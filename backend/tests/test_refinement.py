from intellidocpro.prompts import (
    LLMRefinedField,
    LLMRefinementOperation,
    LLMRefinementPlan,
    LLMRefinementRejection,
    REFINE_SYSTEM,
    SUGGEST_SYSTEM,
    refine_user_prompt,
)
from intellidocpro.refinement import apply_refinement_plan
from intellidocpro.schema import ExtractionSchema, FieldSpec, FieldType, SchemaChatMessage


def refined_field(
    name: str,
    field_type: FieldType = FieldType.TEXT,
    *,
    key: str | None = None,
    enum_values: list[str] | None = None,
    required: bool = False,
) -> LLMRefinedField:
    return LLMRefinedField(
        name=name,
        key=key,
        type=field_type,
        description=None,
        enum_values=enum_values,
        required=required,
    )


def operation(
    action: str,
    *,
    target: str | None = None,
    field: LLMRefinedField | None = None,
    evidence: str | None = None,
    page: int | None = None,
    update_fields: list[str] | None = None,
) -> LLMRefinementOperation:
    return LLMRefinementOperation(
        action=action,
        target_name=target,
        field=field,
        update_fields=update_fields or [],
        evidence_text=evidence,
        evidence_page=page,
        reason="test",
    )


def plan(
    *operations: LLMRefinementOperation,
    rejections: list[LLMRefinementRejection] | None = None,
    message: str = "Done",
) -> LLMRefinementPlan:
    return LLMRefinementPlan(
        operations=list(operations),
        rejections=rejections or [],
        message=message,
    )


def test_add_requires_sample_evidence_and_supports_partial_success():
    current = ExtractionSchema(fields=[FieldSpec(name="Lieferant", required=True)])
    result = apply_refinement_plan(
        current,
        plan(
            operation(
                "add",
                field=refined_field("Zahlungsziel", FieldType.DATE),
                evidence="Zahlungsziel: 2026-08-13",
                page=1,
            ),
            operation("add", field=refined_field("Interner Genehmiger")),
        ),
    )

    assert [field.name for field in result.schema.fields] == ["Lieferant", "Zahlungsziel"]
    assert result.schema.fields[0].required is True
    assert result.changed is True
    assert result.applied == ["Added field: Zahlungsziel"]
    assert result.rejected[0].request == "Interner Genehmiger"
    assert "Interner Genehmiger" in result.message


def test_add_rejects_non_positive_evidence_page():
    current = ExtractionSchema(fields=[FieldSpec(name="A")])
    result = apply_refinement_plan(
        current,
        plan(
            operation(
                "add",
                field=refined_field("B"),
                evidence="B: visible",
                page=-1,
            )
        ),
    )
    assert result.schema == current
    assert result.rejected[0].request == "B"


def test_add_removes_trailing_label_colon():
    current = ExtractionSchema(fields=[FieldSpec(name="A")])
    result = apply_refinement_plan(
        current,
        plan(
            operation(
                "add",
                field=refined_field("Zahlungsziel:"),
                evidence="Zahlungsziel: 30 Tage",
                page=1,
            )
        ),
    )
    assert result.schema.fields[-1].name == "Zahlungsziel"


def test_update_keeps_position_and_unrelated_fields_exactly():
    untouched = FieldSpec(
        name="Lieferant",
        description="Exact hint",
        required=True,
    )
    target = FieldSpec(
        name="Datum",
        description="Keep this exact hint",
        required=True,
    )
    current = ExtractionSchema(fields=[untouched, target])
    result = apply_refinement_plan(
        current,
        plan(
            operation(
                "update",
                target="Datum",
                field=refined_field("Rechnungsdatum", FieldType.DATE),
                update_fields=["name", "type"],
            )
        ),
    )

    assert result.schema.fields[0] == untouched
    assert [field.name for field in result.schema.fields] == [
        "Lieferant",
        "Rechnungsdatum",
    ]
    assert result.schema.fields[1].description == "Keep this exact hint"
    assert result.schema.fields[1].required is True


def test_duplicate_rename_and_deleting_last_field_are_rejected():
    current = ExtractionSchema(fields=[FieldSpec(name="A"), FieldSpec(name="B")])
    duplicate = apply_refinement_plan(
        current,
        plan(
            operation(
                "update",
                target="B",
                field=refined_field("A"),
                update_fields=["name"],
            )
        ),
    )
    assert duplicate.schema == current
    assert duplicate.rejected[0].reason == "Renaming would create a duplicate field."

    one = ExtractionSchema(fields=[FieldSpec(name="Only")])
    deleted = apply_refinement_plan(one, plan(operation("delete", target="Only")))
    assert deleted.schema == one
    assert deleted.changed is False


def test_invalid_enum_degrades_to_text():
    current = ExtractionSchema(fields=[FieldSpec(name="A")])
    result = apply_refinement_plan(
        current,
        plan(
            operation(
                "add",
                field=refined_field("Status", FieldType.ENUM, enum_values=[]),
                evidence="Status: offen",
                page=1,
            )
        ),
    )
    assert result.schema.fields[1].type == FieldType.TEXT
    assert result.schema.fields[1].enum_values is None


def test_refine_prompt_contains_full_schema_history_and_grounding_policy():
    schema = ExtractionSchema(fields=[FieldSpec(name="Lieferant", required=True)])
    text = refine_user_prompt(
        schema,
        "付款期限 hinzufügen",
        [SchemaChatMessage(role="assistant", content="Vorherige Änderung")],
    )

    assert '"fields"' in text
    assert '"required": true' in text
    assert '"role": "assistant"' in text
    assert "付款期限 hinzufügen" in text
    assert "merely common for this document type is NOT confirmed" in REFINE_SYSTEM


def test_suggest_prompt_requires_verbatim_printed_labels():
    assert "copy the exact printed field label" in SUGGEST_SYSTEM
    assert "Do not translate" in SUGGEST_SYSTEM
    assert "`Gesamt Steuerbetrag` must stay `Gesamt Steuerbetrag`" in SUGGEST_SYSTEM
    assert "`Gesamtbetrag Rechnung` must not become `Gesamtbetrag`" in SUGGEST_SYSTEM
    assert "symbol-only/unit-only labels" in SUGGEST_SYSTEM
    assert "clear semantic name such as `Steuersatz`" in SUGGEST_SYSTEM
    assert "a colon printed at the very end of a label" in SUGGEST_SYSTEM
    assert "`Tel. Nr.:`" in SUGGEST_SYSTEM


def test_prompts_allow_fixed_single_value_table_rows_as_scalar_fields():
    assert "uniquely identifiable row or category shown in a table" in SUGGEST_SYSTEM
    assert "one separate scalar field for every confirmed printed label" in REFINE_SYSTEM
    assert "Do not reject a requested field merely because" in REFINE_SYSTEM
    assert "`Fracht Versandort - Empfangsort`" in REFINE_SYSTEM
    assert "`Road tax`" in REFINE_SYSTEM
    assert "`Fuel Surcharge`" in REFINE_SYSTEM
    assert "Do not propose fields for repeating rows" not in REFINE_SYSTEM
