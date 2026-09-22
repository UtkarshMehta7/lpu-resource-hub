"""PageParams bounds and the Page[T] response shape."""

from __future__ import annotations

from typing import Annotated

import pytest
from fastapi import Depends, FastAPI
from fastapi.testclient import TestClient

from app.core.pagination import MAX_PAGE_SIZE, Page, PageParams


def test_page_params_offset() -> None:
    params = PageParams(page=3, page_size=10)

    assert params.offset == 20


def test_page_shape() -> None:
    page = Page[str](items=["a", "b"], page=1, page_size=20, total=2)

    assert page.model_dump() == {"items": ["a", "b"], "page": 1, "page_size": 20, "total": 2}


def _build_app() -> FastAPI:
    app = FastAPI()

    @app.get("/items")
    def items(params: Annotated[PageParams, Depends()]) -> dict[str, int]:
        return {"page": params.page, "page_size": params.page_size}

    return app


def test_page_params_defaults_through_the_dependency() -> None:
    """`Query(default=...)` only resolves through FastAPI's DI, not direct construction."""
    client = TestClient(_build_app())

    response = client.get("/items")

    assert response.status_code == 200
    assert response.json() == {"page": 1, "page_size": 20}


@pytest.mark.parametrize("page_size", [0, MAX_PAGE_SIZE + 1])
def test_page_size_out_of_bounds_is_rejected(page_size: int) -> None:
    client = TestClient(_build_app())

    response = client.get("/items", params={"page_size": page_size})

    assert response.status_code == 422


def test_page_size_at_the_cap_is_accepted() -> None:
    client = TestClient(_build_app())

    response = client.get("/items", params={"page_size": MAX_PAGE_SIZE})

    assert response.status_code == 200
    assert response.json() == {"page": 1, "page_size": MAX_PAGE_SIZE}
