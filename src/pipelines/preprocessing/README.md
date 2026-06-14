# DOCUMENTATION | DATA-PREPROCESSING

> *This module splits legal documents into hierarchical chunks (articles, clauses, points) and builds three index files for efficient retrieval and relationship tracking. It supports both ordinary laws and amending laws, with special handling for point‑level amendments.*

## A. Sub-modules
### A.1. Chunking

#### A.1.1. Features

1. **Hierarchical chunking**  
   - Documents are split by **articles** (Điều).  
   - If an article contains numbered clauses (khoản), each clause becomes a separate chunk.  
   - Clause chunks longer than `max_chunk_size` are further divided into points (a, b, c …) or, as a fallback, into sentences.

2. **Amending law awareness**  
   - The chunker preserves the original document metadata in every chunk.  
   - The indexing step creates three JSON files that later allow an amendment detection pipeline to locate the exact target of a change (document, article, clause, point).

3. **Stable, content‑based IDs**  
   - Each document is given a deterministic `doc_id` (MD5 of its URL or title+number).  
   - Each chunk gets a stable `chunk_id` that encodes `doc_id`, level, article number, clause number, and point letter.  
   - This ensures that rerunning the pipeline updates (upserts) existing records without duplication.

4. **Three index files**  
   - `document_index.json` : document‑level metadata (title, number, URL, etc.).  
   - `chunk_index.json` : every chunk with its content and location metadata.  
   - `hierarchy.json` : nested structure – `doc_id → article → clause → point → list of chunk_ids` – for fast navigation.

5. **Configurable via YAML + `.env`**  
   - Input file path, output directories, chunk size, and stale‑document cleaning are all set in a configuration file (or overridden by environment variables with the `APP_` prefix).

#### A.1.2. Setup via YAML file

Create a configuration file (e.g. `config/data_preprocessing/chunking_config.yml`):

```yaml
chunking:
  input_file: "data/legal_document/metadata_law_ALL_FILTERED.json"
  output_dir: "data/legal_document"       # where all_chunks.json is saved
  max_chunk_size: 2000                    # characters per chunk (applies to clause splitting)
  index_dir: "data/index"                 # where the three index JSON files are written
  clean_stale: false                      # if true, removes old documents no longer in input
```

All values can be overridden with environment variables, e.g.  
`export APP_CHUNKING__MAX_CHUNK_SIZE=2500`.

#### A.1.3. Usage

Run the pipeline from the project root:

```bash
python -m src.pipelines.preprocessing.chunking_pipeline
```

It will read the filtered crawler output (e.g., `metadata_law_ALL_FILTERED.json`), produce `all_chunks.json`, and then generate the three index files in `index_dir`.

#### A.1.4. Output files

| File | Description |
|------|-------------|
| `all_chunks.json` | A flat list of all chunks, each containing document metadata, level, article/clause/point numbers, and the chunk content. |
| `document_index.json` | Maps `doc_id` to document metadata (title, number, URL, last update). |
| `chunk_index.json` | Maps `chunk_id` to the full chunk record (including `doc_id` and location fields). |
| `hierarchy.json` | A nested dictionary: `doc_id → article_number → clause_number → point → list of chunk_ids`. |

A typical chunk in `chunk_index.json` looks like:

```json
{
  "chunk_id": "ac2b53d52a79dc25__clause__art1__cl4__pt0",
  "doc_id": "ac2b53d52a79dc25",
  "level": "clause",
  "article_number": "1",
  "article_title": "Sửa đổi, bổ sung Luật Doanh nghiệp",
  "clause_number": "4",
  "chunk_content": "4. Sửa đổi, bổ sung khoản 2 Điều 13 như sau:\n\"2. Người đại diện theo pháp luật ...\"",
  "Tên văn bản": "Luật Sửa đổi, bổ sung một số điều của Luật Doanh nghiệp số 76/2025/QH15",
  "url": "https://vbpl.vn/..."
}
```

#### A.1.5. Integration with downstream tasks

- **Retrieval (RAG)** : use `chunk_index.json` for semantic search (embeddings can be added later).  
- **Amendment tracking** : use `chunk_id` and the three indexes to locate which documents, articles, clauses, or points are affected by an amending law.  
- **Incremental updates** : because IDs are content‑based, rerunning the pipeline with new or modified documents will automatically upsert existing entries and, if `clean_stale` is enabled, delete documents no longer present.

#### A.1.6. Logging

All steps are logged using the project’s central logger (see `src.utils.log`). You will see progress bars with `tqdm` and detailed output about the number of chunks created and the saved indexes.

For production use, you can adjust the logging level in the main configuration file (under `app.log_level`).

### A.2. Amendment detection

> *This sub-module identifies amendment clauses within amending laws, parses their target (document, article, clause, point), and builds a graph of amendment relationships. It uses the three index files produced by the chunking module.*

#### A.2.1. Features

1. **Automatic amendment recognition**  
   - Scans all clause‑level chunks (`level = "clause"`) for Vietnamese amendment keywords: `"Sửa đổi"`, `"Bổ sung"`, `"Bãi bỏ"`, `"Thay thế"`, etc.

2. **Target extraction**  
   - Extracts the **affected document** (by law number or title) from the clause text or from the parent document’s preamble.  
   - Extracts the **exact location** of the change: article (Điều), clause (khoản), and point (điểm a, b, c…).  
   - Handles both explicit references (`“Luật Doanh nghiệp số 59/2020/QH14”`) and implicit references (`“Luật này”`).

3. **Point‑level support**  
   - If a point is specified (e.g., `“điểm a khoản 2 Điều 5”`), the module tries to locate the corresponding point chunk.  
   - If no dedicated point chunk exists, it extracts the point content directly from the clause chunk using regular expressions.

4. **Relationship output**  
   - Produces `amendment_relations.json` – a list of objects linking the **source** (amending clause) to the **target** (document/article/clause/point) and storing the amendment type.

5. **Integration with indexes**  
   - Uses `document_index.json` to resolve law numbers or titles into `doc_id`.  
   - Uses `hierarchy.json` and `chunk_index.json` to locate the exact target chunk.

#### A.2.2. Configuration

No separate YAML section is required for amendment detection alone. It is part of the main preprocessing pipeline (see **B. main.py**). However, if you wish to run the amendment detection standalone, you can point to the index directory and output file in the configuration:

```yaml
preprocessing:
  index_dir: "data/index"
  amendment_relations_file: "data/amendment_relations.json"
```

#### A.2.3. Usage (standalone)

```bash
python -m src.pipelines.preprocessing.utils.amendment_pipeline --chunk-id "ac2b53d52a79dc25__clause__art1__cl4__pt0"
```

Or to detect all amendments across the entire collection:

```bash
python -m src.pipelines.preprocessing.main   # see section B
```

#### A.2.4. Output format – `amendment_relations.json`

The file is an array of objects, each representing one amendment clause:

```json
[
  {
    "source_chunk_id": "ac2b53d52a79dc25__clause__art1__cl4__pt0",
    "source_doc_id": "ac2b53d52a79dc25",
    "amendment_type": "Sửa đổi, bổ sung",
    "target_doc_id": "94db3067e40fab04",
    "target_article": "13",
    "target_clause": "2",
    "target_point": null,
    "target_chunk_id": "94db3067e40fab04__clause__art13__cl2__pt0",
    "description": "4. Sửa đổi, bổ sung khoản 2 Điều 13 như sau..."
  },
  ...
]
```

| Field | Description |
|-------|-------------|
| `source_chunk_id` | ID of the clause that contains the amendment text. |
| `source_doc_id` | ID of the amending document. |
| `amendment_type` | Type of change (`Sửa đổi`, `Bổ sung`, `Bãi bỏ`, `Thay thế`). |
| `target_doc_id` | ID of the document being amended (may be `null` if not found). |
| `target_article` | Article number (as string, e.g., `"13"`). |
| `target_clause` | Clause number (or `null` if not applicable). |
| `target_point` | Point letter (or `null`). |
| `target_chunk_id` | ID of the exact chunk being amended (if found). |
| `description` | First 300 characters of the clause for inspection. |

#### A.2.5. Limitations and future improvements

- **Ambiguous target documents** – If a law title is generic (e.g., “Luật Doanh nghiệp”), the module may match the wrong document. A future improvement could use the issue date or a disambiguation step.  
- **Partial coverage** – Only laws named “Luật” are currently tracked; other document types (Nghị định, Thông tư) are not yet included.  
- **Resolution of “Luật này”** – Relies on the preamble of the amending law, which must contain the exact target law number. If missing, the target remains unresolved.

---

## B. Main preprocessing pipeline (`main.py`)

> *This orchestration script runs the **chunking** and **amendment detection** sub‑modules in sequence, producing the three index files and the amendment relations from a raw input JSON file.*

### B.1. What it does

1. Loads the filtered crawler output (`metadata_law_ALL_FILTERED.json`).  
2. Runs **chunking** on every document, generating `all_chunks.json` and the three indexes.  
3. Runs **amendment detection** on all clause chunks, producing `amendment_relations.json`.  
4. (Optionally) cleans stale documents if `clean_stale: true`.  
5. Logs progress and timing for each stage.

### B.2. Configuration

Add a `preprocessing` section to your `config/deployment/system.yml`:

```yaml
preprocessing:
  input_file: "data/legal_document/metadata_law_ALL_FILTERED.json"
  output_dir: "data/legal_document"          # for all_chunks.json
  index_dir: "data/index"                    # for the three index files
  max_chunk_size: 2000
  clean_stale: false
  amendment_relations_file: "data/amendment_relations.json"
```

All values can be overridden with environment variables using the `APP_PREPROCESSING__` prefix.

### B.3. Usage

```bash
python -m src.pipelines.preprocessing.main
```

### B.4. Output files

The script produces the following files (depending on configuration):

- `data/legal_document/all_chunks.json` (raw chunks)  
- `data/index/document_index.json`  
- `data/index/chunk_index.json`  
- `data/index/hierarchy.json`  
- `data/amendment_relations.json`  

### B.5. Dependency graph

```
metadata_law_ALL_FILTERED.json
            │
            ▼
    ┌───────────────┐
    │  chunking     │
    └───────────────┘
            │
            ├──► all_chunks.json
            ├──► document_index.json
            ├──► chunk_index.json
            └──► hierarchy.json
                      │
                      ▼
              ┌───────────────┐
              │ amendment     │
              │ detection     │
              └───────────────┘
                      │
                      ▼
            amendment_relations.json
```

### B.6. Logging example

```
2025-01-15 10:00:01 | INFO     | preprocessing_main | Loading documents from data/legal_document/metadata_law_ALL_FILTERED.json
2025-01-15 10:00:01 | INFO     | preprocessing_main | Loaded 12 documents
Chunking documents: 100%|██████████| 12/12 [00:00<00:00, 816.73it/s]
2025-01-15 10:00:02 | INFO     | preprocessing_main | Total chunks created: 3315
2025-01-15 10:00:02 | INFO     | preprocessing_main | Saved raw chunks to data/legal_document/all_chunks.json
2025-01-15 10:00:02 | INFO     | preprocessing_main | Building document, chunk, and hierarchy indexes
2025-01-15 10:00:02 | INFO     | preprocessing_main | Saved document index: 12 documents
2025-01-15 10:00:02 | INFO     | preprocessing_main | Saved chunk index: 3315 chunks
2025-01-15 10:00:02 | INFO     | preprocessing_main | Saved hierarchy tree
2025-01-15 10:00:02 | INFO     | preprocessing_main | Detecting amendment relationships
Detecting amendments: 100%|██████████| 3315/3315 [00:00<00:00, 12456.78it/s]
2025-01-15 10:00:03 | INFO     | preprocessing_main | Found 28 amendment relations
2025-01-15 10:00:03 | INFO     | preprocessing_main | Saved amendment relations to data/amendment_relations.json
2025-01-15 10:00:03 | INFO     | preprocessing_main | Preprocessing pipeline finished successfully.
```

### B.7. Extensibility

- **Add new preprocessing steps** – Insert them between chunking and amendment detection, or after amendment detection, by modifying the `main()` function.  
- **Support other document types** – Extend the amendment detection regexes and lookup logic to handle Nghị định, Thông tư, etc.  
- **Output to database** – Replace the JSON file outputs with direct PostgreSQL inserts (using the database client described in section III).