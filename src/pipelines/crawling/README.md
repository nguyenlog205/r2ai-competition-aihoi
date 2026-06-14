## DOCUMENTATION | DATA CRAWLING
> *This module ingests legal documents from the Vietnamese legal database vbpl.vn. It automates search, filtering, metadata extraction, and content harvesting for downstream processing.*

### 1. Features
(a). Keyword‑based search – queries the portal for user‑defined terms (e.g., "luật đất đai").

(b). Automatic filtering – only keeps documents that:
- Are not marked as fully expired ("Hết hiệu lực toàn bộ").
- Have a title containing "luật" or "sửa đổi" (configurable).

(c) Extracts:
- Full text content (from the preview‑content area).
- Metadata: title, document number, issuing authority, effective date, etc. (from the luoc‑do tab).

(d). Pagination handling – traverses result pages until the configured limit is reached or no “Next” button exists.

(e). Persistent storage – saves per‑keyword JSON files and merges them into a single deduplicated file (metadata_law_ALL.json).

(f). Headless mode – can run without a visible browser window for server environments.

### 2. Setup via YAML-file and usage
To run, first create a YAML configuration file (example: config/data_preprocessing/crawl_config.yml):
```yml
crawl:
  search_keywords:
    - "luật đất đai"
    - "luật doanh nghiệp"
    - "luật đầu tư"
  output_dir: "data/legal_document"   # relative to project root
  limit_page: 300                     # max pages per keyword (default: 300)
  webpage_link: "https://vbpl.vn/pages/portal.aspx"
  headless: false                     # set true to run without GUI
```

Then run the crawler from the project root:
```bash
python -m src.pipelines.crawling.main --config_file config/data_preprocessing/crawl_config.yml
```

The crawler creates the following files inside `output_dir`:
|File|	Description|
|-|-|
|`metadata_law_<keyword>.json`|	Raw, filtered data for a single keyword (e.g., `metadata_law_luật_đất_đai.json`).|
|`metadata_law_ALL.json`	|Merged and deduplicated collection (by url) of all keyword results.|

Each JSON file is an array of objects with these fields:
```json
{
  "Tên văn bản": "Luật Đất đai 2024",
  "Số hiệu": "31/2024/QH15",
  "Cơ quan ban hành": "Quốc hội",
  "Ngày ban hành": "18/01/2024",
  "Ngày hiệu lực": "01/01/2025",
  "Trạng thái": "Còn hiệu lực",
  "url": "https://vbpl.vn/...",
  "nội dung": "Toàn bộ nội dung văn bản..."
}
```
> **Note**: The exact set of metadata fields depends on what the portal provides in the luoc‑do tab.