"""Kit lifecycle and undo orchestration around the stage-local coloring engine."""

import asyncio
from time import perf_counter
import weakref

import carb
import omni.kit.app
import omni.kit.commands
import omni.usd

from .discovery import HOOPS, Scan, scan_steps
from .overrides import ApplyReport, ColorOverrides
from .appearance import Appearance
from .presets import dumps, load_scene, loads, save_scene
from .scheme import Scheme, group_objects


class ChangeObjectColors(omni.kit.commands.Command):
    def __init__(self, controller, before: str, after: str):
        self.controller = weakref.ref(controller)
        self.generation = controller.generation
        self.before = before
        self.after = after

    def _restore(self, text):
        controller = self.controller()
        if controller and controller.generation == self.generation and controller.alive:
            controller.restore(text)

    def do(self):
        self._restore(self.after)

    def undo(self):
        self._restore(self.before)


class InspectionScope:
    """Exclusive, stage-bound use of the controller's material override layer."""

    def __init__(self, controller, stage):
        self._controller = weakref.ref(controller)
        self._stage = stage
        self._generation = controller.generation
        self._task = None
        self._close_task = None
        self._closed = False
        self._intent = 0

    def _owner(self):
        controller = self._controller()
        if (controller is None or self._closed or controller._inspection is not self
                or controller.generation != self._generation
                or not controller._stage_matches(self._stage)):
            raise RuntimeError('The Object Colors inspection scope is no longer bound to this stage.')
        return controller

    def _invalidate(self):
        self._closed = True
        if self._task:
            self._task.cancel()

    async def apply(self, assignments: dict[str, str | Appearance]) -> ApplyReport:
        """Replace the temporary highlight; an empty mapping reveals source materials."""
        self._owner()
        colors = {path: value if isinstance(value, Appearance) else Appearance(value)
                  for path, value in assignments.items()}
        self._intent += 1
        intent = self._intent
        if self._task:
            self._task.cancel()
            await asyncio.gather(self._task, return_exceptions=True)
        self._owner()
        if intent != self._intent:
            raise asyncio.CancelledError('A newer inspection highlight superseded this one.')
        task = asyncio.ensure_future(self._apply(colors))
        self._task = task
        try:
            return await task
        finally:
            if self._task is task:
                self._task = None

    async def _apply(self, assignments):
        controller = self._owner()
        await controller._cancel_update()
        async with controller._operation_lock:
            controller = self._owner()
            overrides = controller.overrides
            if not assignments:
                overrides.set_enabled(False)
                report = ApplyReport()
            else:
                previous_enabled = overrides.enabled
                overrides.enabled = True
                try:
                    report = await controller._drive(overrides.apply_steps(assignments), 'Applying project highlight')
                except BaseException:
                    if not overrides.closed:
                        overrides.set_enabled(previous_enabled)
                    raise
            self._owner()
            controller.status = (f'Project highlight: {report.colored:,} colored, '
                                 f'{report.unsupported:,} unsupported')
            controller.notify(False)
            return report

    async def close(self):
        """Release the display and restore the latest desired Object Colors scheme."""
        if self._close_task is None:
            self._closed = True
            self._intent += 1
            self._close_task = asyncio.ensure_future(self._close())
        await asyncio.shield(self._close_task)

    async def _close(self):
        if self._task:
            self._task.cancel()
            await asyncio.gather(self._task, return_exceptions=True)
        controller = self._controller()
        if controller is not None:
            await controller._finish_inspection(self)


class Controller:
    def __init__(self):
        self.stage = None
        self.overrides = None
        self.scheme = Scheme()
        self.scan = Scan()
        self.groups = []
        self.status = 'Open a USD stage to discover object properties.'
        self.issues = []
        self.busy = False
        self.generation = 0
        self.alive = True
        self.listeners = []
        self.task = None
        self._operation_lock = asyncio.Lock()
        self._inspection = None
        self.context = omni.usd.get_context()
        self.subscription = self.context.get_stage_event_stream().create_subscription_to_pop(
            self._stage_event, name='object.color.stage')
        self.attach(self.context.get_stage())

    def notify(self, rebuild=True):
        for listener in tuple(self.listeners):
            listener(rebuild)

    @property
    def inspection_active(self) -> bool:
        return self._inspection is not None

    def _stage_matches(self, stage) -> bool:
        return (self.alive and stage is not None and self.stage is not None
                and stage == self.stage and self.context == omni.usd.get_context()
                and stage == self.context.get_stage())

    def begin_inspection(self, stage) -> InspectionScope:
        if not self._stage_matches(stage) or self.overrides is None:
            raise RuntimeError('Object Colors is not attached to this default-context stage.')
        if self._inspection is not None:
            raise RuntimeError('Object Colors already has an active project inspection.')
        scope = InspectionScope(self, stage)
        self._inspection = scope
        if self.task:
            self.task.cancel()
        self.overrides.set_enabled(False)
        self.notify()
        return scope

    async def _cancel_update(self):
        task = self.task
        if task and not task.done():
            task.cancel()
            await asyncio.gather(task, return_exceptions=True)

    async def _finish_inspection(self, scope: InspectionScope):
        await self._cancel_update()
        async with self._operation_lock:
            if (self._inspection is not scope or self.generation != scope._generation
                    or not self._stage_matches(scope._stage)):
                return
            try:
                await self._update_locked(False, self.generation, False)
            except Exception:
                if self.generation == scope._generation and self.overrides is not None:
                    self.overrides.set_enabled(False)
                raise
            finally:
                if self._inspection is scope:
                    self._inspection = None
                self.notify()

    async def get_scan(self, refresh=True) -> Scan:
        """Return all discovered objects, without the panel's group limit."""
        stage = self.stage
        generation = self.generation
        if not self._stage_matches(stage):
            raise RuntimeError('Object Colors is not attached to the default-context stage.')
        if not refresh:
            return self.scan
        await self._cancel_update()
        async with self._operation_lock:
            if generation != self.generation or not self._stage_matches(stage):
                raise RuntimeError('The stage changed while scanning object colors.')
            scan = await self._drive(scan_steps(stage), 'Scanning')
            if generation != self.generation or not self._stage_matches(stage):
                raise RuntimeError('The stage changed while scanning object colors.')
            self.scan = scan
            self.groups = group_objects(scan.objects, self.scheme)
            self.notify()
            return scan

    def _stage_event(self, event):
        if event.type == int(omni.usd.StageEventType.OPENED):
            self.attach(self.context.get_stage())
        elif event.type == int(omni.usd.StageEventType.CLOSING):
            self.attach(None)

    def attach(self, stage):
        self.generation += 1
        if self._inspection:
            self._inspection._invalidate()
            self._inspection = None
        if self.task:
            self.task.cancel()
        if self.overrides:
            self.overrides.close()
        self.stage = stage
        self.overrides = ColorOverrides(stage) if stage else None
        self.scan = Scan()
        self.groups = []
        self.busy = False
        self.issues = []
        try:
            self.scheme = load_scene(stage) if stage else Scheme()
        except ValueError as exc:
            self.scheme = Scheme()
            self.issues = [f'Saved scene colors could not be loaded: {exc}']
        if stage:
            self._schedule(True, persist=False)
        else:
            self.status = 'Open a USD stage to discover object properties.'
            self.notify()

    def edit(self, *, mode=None, property_key=None, enabled=None, color=None):
        _, scheme = loads(dumps('Current', self.scheme))
        if mode is not None:
            scheme.mode = mode
        if property_key is not None:
            scheme.property_key = property_key
        if enabled is not None:
            scheme.enabled = enabled
        if color is not None:
            scheme.set_color(*color)
        self.change(scheme)

    def change(self, scheme):
        omni.kit.commands.execute('ChangeObjectColors', controller=self,
                                  before=dumps('Current', self.scheme), after=dumps('Current', scheme))

    def restore(self, text):
        _, self.scheme = loads(text)
        if self._inspection is not None and self.stage is not None:
            self.groups = group_objects(self.scan.objects, self.scheme)
            self.issues = list(self.scan.issues)
            if not save_scene(self.stage, self.scheme):
                self.issues.append('Scene is read-only. Color choices cannot be saved to this scene.')
            self.status = 'Object Colors scheme saved; display suspended by Project View.'
            self.notify()
        else:
            self._schedule(False)

    def refresh(self):
        self._schedule(True)

    def _schedule(self, rescan, persist=True):
        if not self.stage:
            return
        if self.task:
            self.task.cancel()
        self.task = asyncio.ensure_future(self._update(rescan, self.generation, persist))

    async def _drive(self, steps, label):
        try:
            while True:
                try:
                    progress = next(steps)
                except StopIteration as done:
                    return done.value
                self.status = f'{label} {progress:.0%}' if isinstance(progress, float) else f'{label} {progress:,} prims'
                self.notify(False)
                await omni.kit.app.get_app().next_update_async()
        finally:
            steps.close()

    async def _update(self, rescan, generation, persist):
        async with self._operation_lock:
            if generation != self.generation or self.stage is None:
                return
            self.busy = True
            self.notify()
            try:
                await self._update_locked(rescan, generation, persist)
            except asyncio.CancelledError:
                raise
            except Exception as exc:
                self.status = f'Could not update colors: {exc}'
                self.issues.append(str(exc))
                carb.log_error(self.status)
            finally:
                if generation == self.generation and asyncio.current_task() is self.task:
                    self.busy = False
                    self.notify()

    async def _update_locked(self, rescan, generation, persist):
        start = perf_counter()
        stage = self.stage
        overrides = self.overrides
        if stage is None or overrides is None:
            return
        if rescan:
            scan = await self._drive(scan_steps(stage), 'Scanning')
            if generation != self.generation:
                return
            self.scan = scan
            if not self.scheme.property_key and self.scan.properties:
                self.scheme.property_key = (HOOPS + 'TYPE' if HOOPS + 'TYPE' in self.scan.properties else self.scan.properties[0])
        self.groups = group_objects(self.scan.objects, self.scheme)
        self.issues = list(self.scan.issues)
        reason = self.scan.unavailable_reason(self.scheme.mode)
        if self.scheme.mode == 'Property' and self.scheme.property_key not in self.scan.properties:
            reason = 'The selected property is absent. Choose a property or load a compatible scene.'
        if reason:
            self.issues.append(reason)
        if self._inspection is not None and not self._inspection._closed:
            detail = 'Scheme display suspended by Project View'
        elif self.scheme.enabled and not reason:
            colors = {p: g.color for g in self.groups for p in g.objects}
            assignments = {path: color for path, color in colors.items() if color is not None}
            overrides.enabled = True
            report = await self._drive(overrides.apply_steps(assignments), 'Applying colors')
            if generation != self.generation:
                return
            self.issues.extend(report.issues)
            detail = f'{report.colored:,} Xforms colored'
        else:
            overrides.set_enabled(False)
            detail = 'Colors off' if not self.scheme.enabled else 'No colors applied'
        if persist and not save_scene(stage, self.scheme):
            self.issues.append('Scene is read-only. Color choices cannot be saved to this scene.')
        self.status = f'{len(self.scan.objects):,} objects | {detail} | {perf_counter() - start:.2f}s'

    def close(self):
        self.alive = False
        self.generation += 1
        if self._inspection:
            self._inspection._invalidate()
            self._inspection = None
        self.subscription = None
        if self.task:
            self.task.cancel()
            self.task = None
        if self.overrides:
            self.overrides.close()
            self.overrides = None
        self.listeners.clear()
        self.stage = None
