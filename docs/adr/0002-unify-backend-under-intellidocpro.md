# Unify the backend under IntelliDocPro

The open-source project has one public identity: IntelliDocPro. The backend directory becomes `backend`, the installable Python package becomes `intellidocpro`, Document Agents replace Assistants in the UI and API, and the legacy `docstill` name receives no compatibility aliases; during the MVP this is a naming migration only, so the existing `server` boundary remains instead of introducing a new architecture.
