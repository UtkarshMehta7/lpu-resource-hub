"""Personal request endpoints, mounted under /api/v1.

No permission dependency anywhere here, and that is deliberate: whether you
may put a request to somebody is not a thing you hold, it is a fact about the
two roles and the two departments. `REQUEST_RECIPIENT_ROLES` plus the
department check in `policies.addressable_filter` is the enforcement, and it
runs on the named recipient rather than on the caller alone.

`/requests/recipients` and `/requests/inbox` are registered BEFORE
`/requests/{request_id}`. A nested literal loses to a path parameter
registered first -- FastAPI matches in registration order, and "inbox" would
be parsed as a UUID. The trap `/publications/duplicates` fell into.
"""

from __future__ import annotations

import uuid
from collections.abc import Iterator
from contextlib import contextmanager
from typing import Annotated
from urllib.parse import quote

from fastapi import (
    APIRouter,
    Depends,
    File,
    HTTPException,
    Query,
    Request,
    Response,
    UploadFile,
    status,
)
from sqlalchemy.orm import Session

from app.core.config import Settings, get_settings
from app.core.deps import get_current_user
from app.core.pagination import Page, PageParams
from app.core.rate_limit import enforce_collaboration_rate_limit
from app.db.session import get_db
from app.modules.requests import service
from app.modules.requests.models import RequestStatus
from app.modules.requests.schemas import (
    InboxCount,
    RequestCreate,
    RequestRead,
    RequestRecipient,
    RequestStatusChange,
)
from app.modules.uploads import validation
from app.modules.users.models import User

router = APIRouter(tags=["requests"])

DbSession = Annotated[Session, Depends(get_db)]
CurrentUser = Annotated[User, Depends(get_current_user)]
AppSettings = Annotated[Settings, Depends(get_settings)]

_NOT_FOUND = HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Request not found.")


@contextmanager
def _domain_errors() -> Iterator[None]:
    try:
        yield
    except service.RequestNotFoundError as exc:
        raise _NOT_FOUND from exc
    except service.UnknownRecipientError as exc:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
            detail=(
                "You cannot put a request to that person. A request goes to "
                "somebody above you in your own department, or to the Dean of "
                "Research or an administrator."
            ),
        ) from exc
    except service.ImpossibleMoveError as exc:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="This request is not in a state where that can happen.",
        ) from exc
    except service.NotYourMoveError as exc:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="That is the other party's to do.",
        ) from exc
    except service.ReasonRequiredError as exc:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
            detail="Declining a request requires a reason.",
        ) from exc


@router.get("/requests/recipients", response_model=list[RequestRecipient])
def read_recipients(db: DbSession, sender: CurrentUser) -> list[RequestRecipient]:
    """Who you may put a request to.

    Filtered by the same rules the submit enforces, so the picker can never
    offer somebody the submit would refuse. An empty list is a real answer:
    an administrator addresses nobody.
    """
    return service.addressable(db, sender)


@router.get("/requests/inbox", response_model=Page[RequestRead])
def read_inbox(
    db: DbSession,
    viewer: CurrentUser,
    params: Annotated[PageParams, Depends()],
    status_filter: Annotated[RequestStatus | None, Query(alias="status")] = None,
) -> Page[RequestRead]:
    """Requests put to you, newest first."""
    return service.list_inbox(db, params, viewer, status=status_filter)


@router.get("/requests/inbox/count", response_model=InboxCount)
def read_inbox_count(db: DbSession, viewer: CurrentUser) -> InboxCount:
    """What you still owe an answer on. Drives the badge."""
    return InboxCount(waiting=service.waiting_count(db, viewer))


@router.get("/me/requests", response_model=Page[RequestRead])
def read_sent(
    db: DbSession,
    viewer: CurrentUser,
    params: Annotated[PageParams, Depends()],
    status_filter: Annotated[RequestStatus | None, Query(alias="status")] = None,
) -> Page[RequestRead]:
    """Requests you have sent, newest first."""
    return service.list_sent(db, params, viewer, status=status_filter)


@router.post("/requests", response_model=RequestRead, status_code=status.HTTP_201_CREATED)
def create_request(
    data: RequestCreate, request: Request, db: DbSession, sender: CurrentUser
) -> RequestRead:
    """Put a request to a named person above you."""
    # Shares the collaboration budget, like nudges: both are "this account is
    # generating notifications for other people", and that is the thing worth
    # capping.
    enforce_collaboration_rate_limit(request, sender.id)
    with _domain_errors():
        return service.submit(db, sender, data)


@router.get("/requests/{request_id}", response_model=RequestRead)
def read_request(request_id: uuid.UUID, db: DbSession, viewer: CurrentUser) -> RequestRead:
    with _domain_errors():
        return service.get_request(db, request_id, viewer)


@router.post("/requests/{request_id}/status", response_model=RequestRead)
def change_status(
    request_id: uuid.UUID, data: RequestStatusChange, db: DbSession, actor: CurrentUser
) -> RequestRead:
    """Take it up, answer it, refuse it -- or, as the sender, withdraw it."""
    with _domain_errors():
        return service.change_status(db, request_id, actor, data.status, data.note)


@router.post(
    "/requests/{request_id}/attachments",
    response_model=RequestRead,
    status_code=status.HTTP_201_CREATED,
)
def add_attachment(
    request_id: uuid.UUID,
    db: DbSession,
    actor: CurrentUser,
    settings: AppSettings,
    file: Annotated[UploadFile, File(description="A supporting document.")],
) -> RequestRead:
    data = file.file.read(settings.upload_max_bytes + 1)
    with _domain_errors():
        try:
            return service.add_attachment(
                db,
                request_id,
                actor,
                data=data,
                filename=file.filename,
                max_bytes=settings.upload_max_bytes,
            )
        except validation.EmptyFileError as exc:
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_CONTENT, detail="That file is empty."
            ) from exc
        except validation.FileTooLargeError as exc:
            raise HTTPException(
                status_code=status.HTTP_413_CONTENT_TOO_LARGE,
                detail=(
                    f"That file is larger than {exc.limit // (1024 * 1024)} MB. Link to it instead."
                ),
            ) from exc
        except validation.UnsupportedFileTypeError as exc:
            raise HTTPException(
                status_code=status.HTTP_415_UNSUPPORTED_MEDIA_TYPE,
                detail=f"That file type is not accepted. Allowed: {validation.ALLOWED_LABELS}.",
            ) from exc


@router.delete(
    "/requests/{request_id}/attachments/{attachment_id}",
    status_code=status.HTTP_204_NO_CONTENT,
)
def remove_attachment(
    request_id: uuid.UUID, attachment_id: uuid.UUID, db: DbSession, actor: CurrentUser
) -> None:
    with _domain_errors():
        service.remove_attachment(db, request_id, attachment_id, actor)


@router.get(
    "/requests/{request_id}/attachments/{attachment_id}",
    response_class=Response,
    responses={200: {"content": {"application/octet-stream": {}}}},
)
def download_attachment(
    request_id: uuid.UUID, attachment_id: uuid.UUID, db: DbSession, viewer: CurrentUser
) -> Response:
    """The file itself, for the two people party to the request.

    Always `Content-Disposition: attachment`: nothing uploaded here is
    rendered in the browser on this origin, so a supporting document cannot
    become a script running as the application.
    """
    with _domain_errors():
        attachment = service.read_attachment(db, request_id, attachment_id, viewer)
    return Response(
        content=attachment.data,
        media_type=attachment.content_type,
        headers={
            "Content-Disposition": (
                f'attachment; filename="{attachment.filename}"; '
                f"filename*=UTF-8''{quote(attachment.filename)}"
            ),
            "Cache-Control": "private, max-age=3600",
            "X-Content-Type-Options": "nosniff",
        },
    )


__all__ = ["router"]
