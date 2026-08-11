from django.views.generic import TemplateView
from web_project import TemplateLayout
from web_project.template_helpers.theme import TemplateHelper


class SystemView(TemplateView):
    template_name = "pages/system/not-found.html"
    status = ""

    def get_context_data(self, **kwargs):
        # A function to init the global layout. It is defined in web_project/__init__.py file
        context = TemplateLayout.init(self, super().get_context_data(**kwargs))

        # Define the layout for this module
        # _templates/layout/system.html
        context.update(
            {
                "layout_path": TemplateHelper.set_layout("system.html", context),
                "status": self.status,
            }
        )

        return context

    def render_to_response(self, context, **response_kwargs):
        # `status` est fourni par les handlers d'erreur (voir config/urls.py).
        # Sans ceci, TemplateView renverrait 200 : la page d'erreur s'afficherait
        # correctement mais annoncerait « tout va bien » aux navigateurs, aux
        # moteurs de recherche et aux outils de supervision.
        if self.status:
            response_kwargs.setdefault("status", int(self.status))
        return super().render_to_response(context, **response_kwargs)
