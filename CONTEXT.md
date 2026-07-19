# IntelliDocPro

IntelliDocPro provides configurable workers for processing business documents.

## Language

**Document Agent**:
A persistent, configurable worker that carries out one or more document-processing responsibilities. An extraction schema or document type may guide a Document Agent, but neither defines its identity.
_Avoid_: Assistant, Extraction Profile, Document Type (when referring to the worker)

**Document**:
A uniquely stored business document. Submitting the same underlying content again refers to the existing Document, and one Document may be processed by multiple Document Agents.
_Avoid_: Upload, file copy

**Extraction**:
The current interpretation of one Document by one Document Agent. There is at most one Extraction for each Document and Document Agent pair; a configuration change makes it stale until a user explicitly reprocesses it.
_Avoid_: Run, historical result

**Run**:
An immutable record of one execution of a Document Agent over a set of documents. Running an Agent again creates another Run rather than changing the earlier record.
_Avoid_: Reusing or overwriting an earlier Run
