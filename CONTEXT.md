# IntelliDocPro

IntelliDocPro provides configurable workers for processing business documents.

## Language

**Document Agent**:
A persistent, configurable worker that carries out one or more document-processing responsibilities. An extraction schema or document type may guide a Document Agent, but neither defines its identity.
_Avoid_: Assistant, Extraction Profile, Document Type (when referring to the worker)

**Run**:
An immutable record of one execution of a Document Agent over a set of documents. Running an Agent again creates another Run rather than changing the earlier record.
_Avoid_: Reusing or overwriting an earlier Run
