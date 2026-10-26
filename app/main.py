import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI, HTTPException, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse

from .api.routes import auth, chats, health, qa, qa_auth, qa_users
from .db.session import engine
from .middleware import ApiSecurityMiddleware, RequestSizeLimitMiddleware

logging.basicConfig(level=logging.INFO)


@asynccontextmanager
async def lifespan(_: FastAPI):
    yield
    if engine is not None:
        engine.dispose()


app = FastAPI(title="QA Insights API", lifespan=lifespan)
app.add_middleware(RequestSizeLimitMiddleware)
app.add_middleware(ApiSecurityMiddleware)
app.include_router(auth.router)
app.include_router(chats.router)
app.include_router(health.router)
app.include_router(qa_auth.router)
app.include_router(qa_users.router)
app.include_router(qa.router)


@app.exception_handler(HTTPException)
async def http_error_handler(_: Request, error: HTTPException) -> JSONResponse:
    return JSONResponse(
        status_code=error.status_code,
        content={"error": error.detail if isinstance(error.detail, str) else "Request failed."},
        headers=error.headers,
    )


@app.exception_handler(RequestValidationError)
async def validation_error_handler(_: Request, error: RequestValidationError) -> JSONResponse:
    if any(item["type"] == "json_invalid" for item in error.errors()):
        message = "The request body is invalid."
    else:
        message = "The request body contains invalid or missing fields."
    return JSONResponse(status_code=400, content={"error": message})


@app.exception_handler(Exception)
async def unhandled_error_handler(_: Request, error: Exception) -> JSONResponse:
    logging.getLogger(__name__).exception("Unhandled API error", exc_info=error)
    return JSONResponse(
        status_code=500,
        content={"error": "The server could not complete this request."},
    )
