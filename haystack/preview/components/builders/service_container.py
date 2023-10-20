import inspect
import json
from typing import Callable, Any, List

from haystack.preview import component


# TODO remove this once we have a proper ChatMessage class
class ChatMessage:
    pass


@component
class ServiceContainer:
    """
    A container for managing a service instance and generating JSON descriptions for its methods.

    The ServiceContainer class is a component that encapsulates a service instance and provides
    functionality for invoking methods on the service instance reflectively based on ChatMessage input,
    as well as generating JSON descriptions for all methods of the service instance according
    to the OpenAI functional API specification.
    """

    def __init__(self, service_instance: Any):
        self.service_instance = service_instance

    def run(self, message: ChatMessage):
        """
        Receives a ChatMessage and calls the corresponding method on the given service instance.


        :param message: The message to process.
        :return: The result of the method call.
        """
        function_name = message.content["name"]
        function_args = json.loads(message.content["arguments"])

        # reflectively call the function
        method = getattr(self.service_instance, function_name, None)
        if method is not None and callable(method):
            # pack arguments
            invocation_args = dict(function_args) if function_args else {}
            return method(**invocation_args)
        else:
            raise ValueError(f"{function_name} is not a method of {self.service_instance.__class__.__name__}")

    def generate_method_description(self) -> List[dict]:
        """
        Generate a list of JSON descriptions for all methods of the service instance.
        These descriptions are usually sent to OpenAI model as part of the functional invocation API.

        :return: A list of JSON strings representing the descriptions as per OpenAI functional API spec.
        """
        return self.generate_descriptions(type(self.service_instance))

    def extract_description(self, docstring: str) -> str:
        """
        Extract the description from a docstring.
        """
        lines = docstring.strip().split("\n")
        description_lines = []
        for line in lines:
            if line.strip().startswith(":"):
                # Stop at the first line that starts with a pydoc notation
                break
            description_lines.append(line)
        return "\n".join(description_lines).strip()

    def generate_description(self, func: Callable[..., Any]) -> str:
        """
        Generate a JSON description for a method according to OpenAI functional API spec.
        :param func: The function to generate a description for.
        :return: A JSON string representing the description as per OpenAI functional API spec.
        """
        func_info = inspect.getfullargspec(func)
        docstring = inspect.getdoc(func)

        if not docstring:
            raise ValueError(f"No docstring provided for function {func.__name__}")

        description = self.extract_description(docstring)

        parameters = {"type": "object", "properties": {}, "required": []}

        for arg in func_info.args:
            if arg == "self":  # Skip 'self' for methods
                continue
            arg_annotation = func_info.annotations.get(arg, None)
            if not arg_annotation:
                raise ValueError(f"No type annotation for parameter {arg} in function {func.__name__}")

            param_info = {"type": str(arg_annotation).lower(), "description": ""}  # Default to empty description

            # Attempt to extract parameter description from docstring
            param_doc = f":param {arg}:"
            if param_doc in docstring:
                param_desc_start = docstring.index(param_doc) + len(param_doc)
                param_desc_end = (
                    docstring.find(":param", param_desc_start) if ":param" in docstring[param_desc_start:] else None
                )
                param_info["description"] = docstring[param_desc_start:param_desc_end].strip()

            # Handle enum type
            if hasattr(arg_annotation, "__members__"):
                param_info["enum"] = list(arg_annotation.__members__.keys())

            parameters["properties"][arg] = param_info

        # Determine required parameters based on defaults
        if func_info.defaults:
            optional_args = func_info.args[-len(func_info.defaults) :]
        else:
            optional_args = []
        parameters["required"] = [arg for arg in func_info.args if arg not in optional_args and arg != "self"]

        representation = {"name": func.__name__, "description": description, "parameters": parameters}

        return json.dumps(representation, indent=4)

    def generate_descriptions(self, cls: type) -> List[dict]:
        """
        Generate a list of JSON descriptions for all methods of a class.
        :param cls: The class to generate descriptions for.
        :return: A list of JSON strings representing the descriptions as per OpenAI functional API spec.
        """
        descriptions = []
        for name, func in inspect.getmembers(cls, predicate=inspect.isfunction):
            json_repr = self.generate_description(func)
            descriptions.append(json.loads(json_repr))
        return descriptions
