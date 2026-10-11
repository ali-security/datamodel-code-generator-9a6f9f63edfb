# Naming

The `server` package serves the Naming API with FastAPI.
datamodel-code-generator generated it from the OpenAPI document, together with the `models` models of the `pydantic_v2.BaseModel` backend.
Generation overwrites every file of the package, as it does the models: keep your code in modules outside the package and regenerate the package instead of editing it; see [Regenerating](#regenerating).

FastAPI server generation is experimental.
The server supports the `pydantic_v2.BaseModel` and `pydantic_v2.dataclass` model backends, while client generation supports all five.
Custom templates, base classes, and Python types stay within these two backends.

## Operations

| Service | Method | HTTP method | Path | Operation reference |
| --- | --- | --- | --- | --- |
| `ItemStoreService` | `get_item` | GET | `/items/{itemId}` | `/paths/~1items~1{itemId}/get` |
| `ItemStoreService` | `get_item_1` | POST | `/items` | `/paths/~1items/post` |
| `ItemStore1Service` | `delete_items_by_item_id_tags` | DELETE | `/items/{itemId}/tags` | `/paths/~1items~1{itemId}~1tags/delete` |
| `Default1Service` | `x1` | GET | `/x1` | `/paths/~1x1/get` |
| `Default1Service` | `x_1` | GET | `/x_1` | `/paths/~1x_1/get` |
| `DefaultService` | `get_health` | GET | `/health` | `/paths/~1health/get` |
| `Default2Service` | `list_defaults` | GET | `/defaults` | `/paths/~1defaults/get` |
| `Default3Service` | `list_upper_defaults` | GET | `/defaults/upper` | `/paths/~1defaults~1upper/get` |
| `UntaggedService` | `list_untagged` | GET | `/untagged` | `/paths/~1untagged/get` |

`operation_dependencies` takes the method names, the keys of `OperationDependencies`; the per-operation generation settings, such as `--server-handler-modes`, take the operation references.

## Implementing the services

`services.py` declares a Protocol for each router group, with an abstract method for each operation of the group.
A method takes the operation's arguments as keywords, with `None` for an optional parameter or body the request omits, and returns the value to send, an `HTTPResult` with another declared status, headers, or both, or a `Response` sent as it is.
Implement each group in a module of your own and pass an instance to `create_app` under the group's name.
Subclass the Protocol, so that type checkers report a missing or mismatched method and Python refuses to create an instance while a method is missing; any other object with the same methods is checked where you pass it.
The package looks each method up when it registers the routes, and refuses a coroutine function where the operation's handler mode needs a plain method, or the reverse; it does not check a method's arguments, so one whose signature type checkers would reject fails when its operation is requested.

```python
from server import create_app
from server.services import ItemStoreService, ItemStore1Service, Default1Service, DefaultService, Default2Service, Default3Service, UntaggedService


class ItemStore(ItemStoreService):
    """Implement `get_item` and `get_item_1`."""


class ItemStore1(ItemStore1Service):
    """Implement `delete_items_by_item_id_tags`."""


class Default1(Default1Service):
    """Implement `x1` and `x_1`."""


class Default(DefaultService):
    """Implement `get_health`."""


class Default2(Default2Service):
    """Implement `list_defaults`."""


class Default3(Default3Service):
    """Implement `list_upper_defaults`."""


class Untagged(UntaggedService):
    """Implement `list_untagged`."""


app = create_app(item_store=ItemStore(), item_store_1=ItemStore1(), default_1=Default1(), default=Default(), default_2=Default2(), default_3=Default3(), untagged=Untagged())
```

Run the application with any ASGI server, such as `uvicorn app:app` for a module named `app.py`.
`create_app` passes its other keyword arguments, such as `lifespan`, `middleware`, or `dependencies`, to `FastAPI`, over the title, version, and other metadata of the source document.
To keep your own `FastAPI` application, include the router:

```python
from fastapi import FastAPI

from server import build_router

app = FastAPI(lifespan=lifespan, exception_handlers=exception_handlers)
app.include_router(build_router(item_store=ItemStore(), item_store_1=ItemStore1(), default_1=Default1(), default=Default(), default_2=Default2(), default_3=Default3(), untagged=Untagged()))
```

## Served OpenAPI document

`create_app` serves the part of the source document the selected operations use, which generation writes into `_generated/openapi.py`; the application reads it on the first request for it.
`create_app(..., source_openapi=False)` serves FastAPI's own document instead, built from the routes and the models they declare, in which an optional parameter or request body is `anyOf` of its type and `null`.
An application of your own that includes `build_router(...)` serves FastAPI's document unless it calls `serve_source_openapi(app)`, imported from `server`.

## Validation

The models are the contract: FastAPI validates parameters, bodies, and responses with the generated model types, so the model generation settings decide how strictly a value follows the OpenAPI document.
Parameter styles, parameter types, and media types that FastAPI cannot read, such as deepObject parameters or cookie arrays, strict integers, numbers, and booleans, text and binary bodies, and multipart forms, pass through generated adapters.
An adapter parses the HTTP syntax, then validates the value with the model's `TypeAdapter`; it answers `400` for malformed syntax, `415` for an undeclared media type, and `422`, with FastAPI's error records, for an invalid value.
A repeated single value is taken as FastAPI takes it, by adapters too: the last query value, cookie, form field, and object member, and the first header.
A cookie parameter with a single value arrives as the request sent it, without percent-decoding.
Adapters accept integers and numbers as JSON writes them and booleans as `true` or `false`, which is fewer spellings than FastAPI accepts for the parameters it reads.

## Production settings

A request that fails validation answers `422` with FastAPI's `{"detail": [...]}` records.
`create_app` keeps the `type`, `loc`, and `msg` of each record and leaves out the `input` and `ctx` FastAPI adds, and pydantic's `url`, so the response does not return the rejected value as such.
`loc` and `msg` are pydantic's and can still hold text the client chose: a mapping key or an unexpected field name, a discriminator tag, or the message of a validator of your own.
An application of your own that includes `build_router(...)` keeps FastAPI's records; register the same handler with `app.add_exception_handler(RequestValidationError, validation_error_handler)`, importing `validation_error_handler` from `server`.
To send other error bodies, pass FastAPI's `exception_handlers` to `create_app`; its entry for `RequestValidationError` replaces the package's.
A result that fails its response model answers `500` without details, and the error, with the values, goes to the server log, as in any FastAPI application.
`create_app(..., docs_url=None, redoc_url=None, openapi_url=None)` removes `/docs`, `/redoc`, and `/openapi.json`.
The `server` response header belongs to the ASGI server, not to the application: uvicorn leaves it out with `--no-server-header`.

## Regenerating

Run the same generation again whenever the OpenAPI document changes; the `--check` option reports the files it would change without writing them.
Generation overwrites every generated file, restoring any you edited or deleted, and never deletes one: delete the modules of removed operations yourself, which `--check` lists as extra files.
When an operation is added, removed, or changed, its method in `services.py` changes with it, so type checkers point at the implementations to update, and Python refuses to create an instance of a subclass that lacks a new method.
Each generation prints the `uv add` command that adds the runtime dependencies of the package to your project;
run it again when a new version of datamodel-code-generator changes them.
