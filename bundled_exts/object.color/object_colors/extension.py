import omni.ext
import omni.kit.commands
import omni.kit.menu.utils

from .controller import ChangeObjectColors, Controller
from .window import ObjectColorsWindow


_live_controller = None


def get_controller():
    """Return the controller owned by the running Object Colors extension, if any."""
    return _live_controller


class ObjectColorsExtension(omni.ext.IExt):
    def on_startup(self, ext_id):
        global _live_controller
        omni.kit.commands.register(ChangeObjectColors)
        self.controller = Controller()
        _live_controller = self.controller
        self.panel = ObjectColorsWindow(self.controller)
        self.menu = [omni.kit.menu.utils.MenuItemDescription(name='Object Colors', onclick_fn=self.panel.show)]
        omni.kit.menu.utils.add_menu_items(self.menu, 'Window')

    def on_shutdown(self):
        global _live_controller
        if _live_controller is self.controller:
            _live_controller = None
        omni.kit.menu.utils.remove_menu_items(self.menu, 'Window')
        self.panel.close()
        self.controller.close()
        omni.kit.commands.unregister(ChangeObjectColors)
