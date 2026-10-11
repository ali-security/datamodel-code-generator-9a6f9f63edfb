"""Call the bodies server through its client: JSON, forms, multipart files and JSON parts, text, and bytes.

Each call names the media type it sends where the operation declares several, and the server reports the model or
value its handler received with the media type it read. Members whose types have no one scalar kind travel as JSON
parts, in a body sent whole and in one sent part by part.
"""

from __future__ import annotations

from itertools import starmap
from typing import TYPE_CHECKING

from tests.api_generation.support.cross_targets import service

if TYPE_CHECKING:
    from types import ModuleType

    from tests.api_generation.support.cross_targets import Calls, Kit, Recorder

DOCUMENT = "fastapi/server-bodies.yaml"
CLIENT = {"default_base_url": "https://bodies.example.com"}


def services(server: ModuleType, models: ModuleType, record: Recorder) -> dict[str, object]:
    """Return a service whose every method records the body it received."""
    del models
    return {"untagged": service(server.services.UntaggedService, record)}


def calls(kit: Kit) -> Calls:
    """Return a call for each media type of each operation, with and without its optional body."""
    api, models, bodies = kit.api.default, kit.models, kit.module("bodies")
    multipart = bodies.AsyncMultipartBody if kit.asynchronous else bodies.MultipartBody
    upload = multipart((
        bodies.FilePart("file", b"\x00binary\xff", filename="a b.bin", content_type="application/octet-stream"),
        bodies.FieldPart("note", "café"),
    ))
    form = models.FieldFormsPostRequest(name="n", tags=["a", "b c"], count=2, extra=5)
    search = models.FieldSearchesPostRequest(
        filter=models.Filter(color="blue", minAge=3),
        filters=[models.Filter(color="a"), models.Filter(minAge=2)],
        tags=["a", "b c"],
        limit=5,
    )
    refused = models.FieldSearchesPostRequest.model_construct(
        filter=models.Filter.model_construct(minAge=-1),
        filters=[models.Filter(), models.Filter.model_construct(minAge=-2)],
    )
    choices = (
        ("text", {"either": "plain", "level": models.Level("a"), "words": "s", "lists": ["x"]}),
        (
            "values",
            {"either": models.Filter(color="c"), "level": models.Level(1), "words": ["a", "b"], "lists": [1, 2]},
        ),
    )
    return [
        ("post_item", lambda: api.post_item(body=models.Item(name="a"))),
        ("post_item without a body", api.post_item),
        ("post_account", lambda: api.post_account(body=models.Account(id=1, name="a"))),
        (
            "post_profile profile=a",
            lambda: api.post_profile(
                body=models.FieldProfilesPostRequest(a=1), media_type="application/json; profile=a"
            ),
        ),
        (
            "post_profile profile=b",
            lambda: api.post_profile(
                body=models.FieldProfilesPostRequest1(b="x"), media_type="application/json; profile=b"
            ),
        ),
        (
            "post_variant JSON",
            lambda: api.post_variant(body=models.FieldVariantsPostRequest1(c=True), media_type="application/json"),
        ),
        (
            "post_variant profile=v1",
            lambda: api.post_variant(
                body=models.FieldVariantsPostRequest(a=1), media_type="application/json; profile=v1"
            ),
        ),
        (
            "post_variant form",
            lambda: api.post_variant(
                body=models.FieldVariantsPostRequest2(tags=["a", "b"]),
                media_type="application/x-www-form-urlencoded",
            ),
        ),
        ("put_document JSON", lambda: api.put_document(body=models.Item(name="j"), media_type="application/json")),
        (
            "put_document vendor JSON",
            lambda: api.put_document(body=models.Item(name="v"), media_type="application/vnd.item+json"),
        ),
        (
            "put_document text",
            lambda: api.put_document(body=models.FieldDocumentsPutRequest("hi"), media_type="text/markdown"),
        ),
        ("put_archive bytes", lambda: api.put_archive(body=b"PK\x03\x04", media_type="application/zip")),
        (
            "put_archive text",
            lambda: api.put_archive(body=models.FieldArchivesPutRequest("abc"), media_type="text/plain"),
        ),
        ("put_blob", lambda: api.put_blob(body=b"\x00\x01\x02")),
        ("post_form", lambda: api.post_form(body=form)),
        ("post_native_form", lambda: api.post_native_form(body=models.FieldNativeFormsPostRequest(name="n"))),
        ("upload", lambda: api.upload(body=upload)),
        ("search", lambda: api.search(body=search)),
        ("search refused parts", lambda: api.search(body=refused)),
        *(
            (f"post_choices {label}", lambda choice=choice: api.post_choices(body=models.Choices(**choice)))
            for label, choice in choices
        ),
        *(
            (
                f"post_choice_files {label}",
                lambda choice=choice: api.post_choice_files(
                    body=multipart(tuple(starmap(bodies.FieldPart, choice.items())))
                ),
            )
            for label, choice in choices
        ),
        ("post_check", lambda: api.post_check(body=models.Check(code=7, scores=[1, 2]))),
        ("post_note null", lambda: api.post_note(body=models.FieldNotesPostRequest(None))),
        ("post_note item", lambda: api.post_note(body=models.FieldNotesPostRequest(models.Item(name="i")))),
        ("post_raw", lambda: api.post_raw(body=models.FieldRawPostRequest())),
    ]
