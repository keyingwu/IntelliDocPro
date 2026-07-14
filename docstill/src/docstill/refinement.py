"""Deterministic application of LLM-proposed schema refinement operations."""

from .prompts import LLMRefinedField, LLMRefinementOperation, LLMRefinementPlan
from .schema import (
    ExtractionSchema,
    FieldSpec,
    FieldType,
    RejectedSchemaRequest,
    SchemaRefinement,
)


def _normalized_field(
    field: LLMRefinedField, *, remove_label_separator: bool = False
) -> FieldSpec:
    field_type = field.type
    enum_values = field.enum_values
    name = field.name.strip()
    if remove_label_separator:
        name = name.rstrip(":：").rstrip()
    if field_type == FieldType.ENUM and not enum_values:
        field_type = FieldType.TEXT
        enum_values = None
    elif field_type != FieldType.ENUM:
        enum_values = None
    return FieldSpec(
        name=name,
        type=field_type,
        description=field.description,
        enum_values=enum_values,
        required=field.required,
    )


def _operation_request(operation: LLMRefinementOperation) -> str:
    if operation.field is not None and operation.field.name.strip():
        return operation.field.name.strip()
    if operation.target_name and operation.target_name.strip():
        return operation.target_name.strip()
    return operation.reason.strip() or operation.action


def _reject(
    rejected: list[RejectedSchemaRequest],
    operation: LLMRefinementOperation,
    reason: str,
) -> None:
    rejected.append(
        RejectedSchemaRequest(request=_operation_request(operation), reason=reason)
    )


def apply_refinement_plan(
    current: ExtractionSchema, plan: LLMRefinementPlan
) -> SchemaRefinement:
    """Apply a provider-neutral operation plan without rewriting untouched fields."""

    fields = [field.model_copy(deep=True) for field in current.fields]
    applied: list[str] = []
    rejected = [
        RejectedSchemaRequest(request=item.request, reason=item.reason)
        for item in plan.rejections
    ]

    for operation in plan.operations:
        names = [field.name for field in fields]

        if operation.action == "add":
            if operation.field is None:
                _reject(rejected, operation, "The add operation did not include a field.")
                continue
            if (
                not (operation.evidence_text or "").strip()
                or operation.evidence_page is None
                or operation.evidence_page < 1
            ):
                _reject(
                    rejected,
                    operation,
                    "The sample did not provide a quoted field reference and page.",
                )
                continue
            try:
                candidate = _normalized_field(
                    operation.field, remove_label_separator=True
                )
            except Exception as exc:
                _reject(rejected, operation, f"The proposed field is invalid: {exc}")
                continue
            if candidate.name in names:
                _reject(rejected, operation, "A field with this name already exists.")
                continue
            fields.append(candidate)
            applied.append(f"Added field: {candidate.name}")
            continue

        target = (operation.target_name or "").strip()
        if not target or target not in names:
            _reject(rejected, operation, "The target field does not exist.")
            continue
        index = names.index(target)

        if operation.action == "delete":
            if len(fields) == 1:
                _reject(rejected, operation, "The schema must keep at least one field.")
                continue
            fields.pop(index)
            applied.append(f"Deleted field: {target}")
            continue

        if operation.field is None:
            _reject(rejected, operation, "The update operation did not include a field.")
            continue
        try:
            current_field = fields[index]
            merged = current_field.model_dump(mode="json")
            proposed = operation.field.model_dump(mode="json")
            for attribute in operation.update_fields:
                merged[attribute] = proposed[attribute]
            candidate = _normalized_field(LLMRefinedField.model_validate(merged))
        except Exception as exc:
            _reject(rejected, operation, f"The proposed field is invalid: {exc}")
            continue
        if candidate.name != target and candidate.name in names:
            _reject(rejected, operation, "Renaming would create a duplicate field.")
            continue
        if candidate == fields[index]:
            continue
        fields[index] = candidate
        applied.append(f"Updated field: {target}")

    schema = ExtractionSchema(fields=fields)
    changed = schema != current
    message = plan.message.strip()
    deterministic_rejections = rejected[len(plan.rejections) :]
    if deterministic_rejections:
        details = "; ".join(
            f"{item.request}: {item.reason}" for item in deterministic_rejections
        )
        message = f"{message} Rejected: {details}.".strip()
    if not message:
        if applied and rejected:
            message = "Some requested changes were applied and some were rejected."
        elif applied:
            message = "The requested schema changes were applied."
        elif rejected:
            message = "The requested changes could not be applied from this sample."
        else:
            message = "No schema changes were needed."

    return SchemaRefinement(
        schema=schema,
        message=message,
        changed=changed,
        applied=applied,
        rejected=rejected,
    )
