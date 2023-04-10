from typing import Optional
from urllib.parse import urljoin

from apispec import BasePlugin, APISpec
from chalice import Blueprint
from pydantic import BaseModel

from chalice_spec.docs import Docs, Operation


class ChalicePlugin(BasePlugin):
    """
    An APISpec plugin which will monkeypatch Chalice in order to allow for very
    convenient API documentation. It is designed to work with in conjunction with
    the PydanticPlugin.

    For example...

    @app.route('/hello',
               post_body_model=APydanticModel,
               post_response_body=APydanticModel)
    def hello():
        return {"world": "The quick brown fox jumps over the lazy dog."}
    """

    def __init__(self, generate_default_docs: bool = False):
        super(ChalicePlugin, self).__init__()
        self._generate_default_docs = generate_default_docs

    def init_spec(self, spec: APISpec) -> None:
        """
        When we initialize the spec, we should also monkeypatch the Chalice app
        we are working with.

        :param spec: APISpec object to work with
        :return: None
        """
        chalice_app = spec.options.pop("chalice_app")

        original_route = chalice_app.route

        def route(path: str, **kwargs):
            """
            Register a new route on a Chalice app. Monekypatched to support APISpec instructions.
            :param path: The path to use.
            :param methods: the allowable methods and their documentation
            :param kwargs: Additional Chalice kwargs and APIspec definitions.
            """
            docs: Docs = kwargs.pop("docs", None)
            methods = [method.lower() for method in kwargs.get("methods", ["get"])]

            if docs is None and self._generate_default_docs:
                docs = Docs(
                    **{
                        method: Operation(
                            response=BaseModel,
                            request=(
                                None
                                if method in ["get", "delete", "head", "options"]
                                else BaseModel
                            ),
                        )
                        for method in methods
                    }
                )

            if docs:
                operations = docs.build_operations(spec, methods)
                spec.path(path, operations=operations, summary=docs.summary)

            return original_route(path, **kwargs)

        def blueprint_route(prefix_url: str):
            def inner_route(path, **kwargs):
                return route(prefix_url + path, **kwargs)

            return inner_route

        original_register_blueprint = chalice_app.register_blueprint

        def register_blueprint(blueprint: Blueprint,
                               name_prefix: Optional[str] = None,
                               url_prefix: Optional[str] = None):
            """
            Register a new blueprint. Blueprints use something akin to an "inversion of control."
            The main Chalice app maintains no state of the blueprints that are registered to it.
            As such, we will have to maintain a list so that we can traverse all the blueprints
            when looking at building our spec.
            """
            blueprint.route = blueprint_route(url_prefix)
            return original_register_blueprint(blueprint, name_prefix=name_prefix, url_prefix=url_prefix)

        chalice_app.route = route
        chalice_app.register_blueprint = register_blueprint
