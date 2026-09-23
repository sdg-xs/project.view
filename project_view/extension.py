"""Kit extension entry point for named construction project views."""

import omni.ext
import omni.kit.menu.utils

from .views import ProjectViews
from .window import ProjectViewWindow


class ProjectViewExtension(omni.ext.IExt):
    def on_startup(self, ext_id):
        self.views = ProjectViews()
        self.panel = ProjectViewWindow(self.views)
        self.menu = [omni.kit.menu.utils.MenuItemDescription(name="Project View", onclick_fn=self.panel.show)]
        omni.kit.menu.utils.add_menu_items(self.menu, "Window")

    def on_shutdown(self):
        omni.kit.menu.utils.remove_menu_items(self.menu, "Window")
        self.panel.destroy()
        self.views.destroy()
