import asyncio
import json
from contextlib import asynccontextmanager
from typing import Annotated, Literal

from fastapi import FastAPI, File, Form, HTTPException, Request, UploadFile
from fastapi.responses import PlainTextResponse, StreamingResponse
from pydantic import BaseModel

from .models import EvidenceDocument, ReplayRequest, ReviewDecision, Transaction
from .service import Service


class InvestigationRequest(BaseModel):
    failure: Literal[
        "none",
        "missing_document",
        "missing_profile",
        "transaction_unavailable",
        "unreadable_document",
        "policy_conflict",
    ] = "none"
    force: bool = False


class ClockRequest(BaseModel):
    as_of: str


def create_app(service=None):
    @asynccontextmanager
    async def lifespan(app):
        app.state.service = service or Service()
        yield
        if service is None:
            app.state.service.close()

    app = FastAPI(title="AML Investigation POC", version="0.1.0", lifespan=lifespan)

    @app.exception_handler(ValueError)
    async def invalid(request: Request, error: ValueError):
        from fastapi.responses import JSONResponse

        return JSONResponse(status_code=409, content={"detail": str(error)})

    def svc(request):
        return request.app.state.service

    @app.get("/health")
    def health(request: Request):
        return {"status": "ok", "mode": svc(request).mode}

    @app.get("/status")
    def status(request: Request):
        return svc(request).status()

    @app.post("/replay/start")
    def start(request: Request, body: ReplayRequest):
        return svc(request).start(**body.model_dump())

    @app.post("/replay/pause")
    def pause(request: Request):
        return svc(request).pause()

    @app.post("/replay/clock")
    def clock(request: Request, body: ClockRequest):
        return svc(request).advance_clock(body.as_of)

    @app.post("/transactions")
    def ingest(request: Request, body: Transaction):
        return svc(request).ingest(body)

    @app.get("/transactions")
    def transactions(request: Request, limit: int = 30):
        return svc(request).recent(min(max(limit, 1), 1000))

    @app.get("/customers")
    def customers(request: Request):
        return [
            {k: v for k, v in customer.items() if k != "assigned_pattern_ids"}
            for customer in svc(request).data.customers.values()
        ]

    @app.get("/customers/{customer_id}/kyc")
    def customer_kyc(request: Request, customer_id: str):
        data = svc(request).data
        customer = data.customers.get(customer_id)
        if customer is None:
            raise HTTPException(404, "Customer not found")
        return {
            "customer": {k: v for k, v in customer.items() if k != "assigned_pattern_ids"},
            "accounts": [a for a in data.accounts.values() if a["customer_id"] == customer_id],
            "counterparties": [
                c for c in data.counterparties.values() if customer_id in c.get("associated_customer_ids", [])
            ],
        }

    @app.get("/alerts")
    def alerts(request: Request, scope: Literal["all", "stream", "history"] = "all"):
        return svc(request).list_alerts(scope)

    @app.get("/alerts/{alert_id}")
    def alert(request: Request, alert_id: str):
        with svc(request).lock:
            result = svc(request).store.get_alert(alert_id)
            if not result:
                raise HTTPException(404, "Alert not found")
            return result

    @app.post("/alerts/{alert_id}/investigate")
    def investigate(request: Request, alert_id: str, body: InvestigationRequest):
        return svc(request).investigate(alert_id, **body.model_dump())

    @app.get("/alerts/{alert_id}/case")
    def case(request: Request, alert_id: str):
        with svc(request).lock:
            return svc(request).store.latest_case(alert_id)

    @app.get("/cases/{case_id}")
    def case_version(request: Request, case_id: str):
        with svc(request).lock:
            result = svc(request).store.get_case(case_id)
            if not result:
                raise HTTPException(404, "Case not found")
            return result

    @app.post("/alerts/{alert_id}/review")
    def review(request: Request, alert_id: str, body: ReviewDecision):
        return svc(request).review(alert_id, body.model_dump())

    @app.post("/alerts/{alert_id}/demo-packet")
    def packet(
        request: Request,
        alert_id: str,
        resolution: Literal["unresolved", "documented_legitimate"] = "unresolved",
    ):
        return svc(request).add_demo_packet(alert_id, resolution=resolution)

    @app.post("/documents")
    def document(request: Request, body: EvidenceDocument):
        return svc(request).add_document(body.model_dump())

    @app.post("/documents/extract")
    async def extract_document(
        request: Request,
        file: Annotated[UploadFile, File()],
        alert_id: Annotated[str, Form()],
        evidence_types: Annotated[str, Form()],
    ):
        from .documents import extract

        try:
            requirements = json.loads(evidence_types)
        except json.JSONDecodeError as error:
            raise HTTPException(422, "evidence_types must be a JSON array") from error
        if (
            not isinstance(requirements, list)
            or not requirements
            or not all(isinstance(item, str) for item in requirements)
        ):
            raise HTTPException(422, "Select at least one evidence requirement")
        content = await file.read(5 * 1024 * 1024 + 1)
        try:
            return await asyncio.to_thread(
                extract,
                svc(request),
                alert_id,
                file.filename or "document",
                file.content_type or "application/octet-stream",
                content,
                requirements,
            )
        except ValueError:
            raise
        except Exception as error:
            raise HTTPException(
                502, "Document extraction failed. No evidence was accepted; inspect the server log."
            ) from error

    @app.get("/audit")
    def audit(request: Request, case_id: str | None = None):
        with svc(request).lock:
            return {
                "valid": svc(request).store.verify_audit(),
                "events": svc(request).store.audit_rows(case_id),
            }

    @app.get("/metrics")
    def metrics(request: Request):
        with svc(request).lock:
            return svc(request).store.metadata("evaluation", {})

    @app.get("/policies")
    def policies(request: Request):
        return {"hash": svc(request).data.policy_hash, "patterns": list(svc(request).data.enabled.values())}

    @app.get("/cases/{case_id}/report", response_class=PlainTextResponse)
    def report(request: Request, case_id: str):
        with svc(request).lock:
            result = svc(request).store.get_case(case_id)
            if not result:
                raise HTTPException(404, "Case not found")
            return result.get("report", "Report is still being assembled.")

    @app.get("/events")
    async def events(request: Request):
        async def generate():
            sequence = 0
            while not await request.is_disconnected():
                snapshot = await asyncio.to_thread(svc(request).status)
                yield f"id: {sequence}\nevent: status\ndata: {json.dumps(snapshot)}\n\n"
                sequence += 1
                await asyncio.sleep(1)

        return StreamingResponse(
            generate(), media_type="text/event-stream", headers={"Cache-Control": "no-cache"}
        )

    from pathlib import Path

    from fastapi.responses import FileResponse
    from fastapi.staticfiles import StaticFiles

    from . import kyc_adapter

    @app.get("/api/customers")
    def dashboard_customers(request: Request):
        return [kyc_adapter.customer(svc(request), k) for k in svc(request).data.customers]

    @app.get("/api/customers/{customer_id}")
    def dashboard_profile(request: Request, customer_id: str):
        if customer_id not in svc(request).data.customers:
            raise HTTPException(404, "Customer not found")
        return kyc_adapter.profile(svc(request), customer_id)

    @app.get("/api/customers/{customer_id}/transactions")
    def dashboard_transactions(
        request: Request,
        customer_id: str,
        limit: int = 50,
        offset: int = 0,
        txn_type: str = "",
        direction: str = "",
        date_from: str = "",
        date_to: str = "",
    ):
        if customer_id not in svc(request).data.customers:
            raise HTTPException(404, "Customer not found")
        rows = [
            r
            for r in kyc_adapter.transactions(svc(request), customer_id)
            if (not txn_type or r["txn_type"] == txn_type)
            and (not direction or r["direction"] == direction)
            and (not date_from or r["txn_ts"][:10] >= date_from)
            and (not date_to or r["txn_ts"][:10] <= date_to)
        ]
        rows.sort(key=lambda r: r["txn_ts"], reverse=True)
        return {
            "total": len(rows),
            "total_usd": sum(r["amount"] for r in rows),
            "rows": rows[max(offset, 0) : max(offset, 0) + min(max(limit, 1), 1000)],
        }

    dashboard = Path(__file__).resolve().parent.parent / "kyc-dashboard" / "dist"
    if dashboard.exists():
        app.mount("/kyc-assets", StaticFiles(directory=dashboard), name="kyc-assets")

        @app.get("/kyc")
        @app.get("/kyc/{customer_id}")
        def dashboard_window():
            return FileResponse(dashboard / "index.html")

    return app


app = create_app()
