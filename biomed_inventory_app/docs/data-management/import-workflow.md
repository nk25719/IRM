# Import Workflow

The import wizard follows:

1. Select Dataset
2. Upload File
3. Map Columns
4. Preview
5. Validate
6. Review Issues
7. Confirm Import
8. Results

Current milestone behavior:

- `.csv` and `.xlsx` files are accepted.
- Unsupported extensions, empty files, duplicate headers, missing headers, and files over 10 MB are rejected.
- Files are stored under `IRM_DATA_ROOT/imports/original/` using generated safe filenames.
- Rows are staged in `import_rows`.
- Blocking validation issues are written to `data_validation_errors`.
- Clean staged batches can be marked `ready_for_execution`.
- Production-table insertion is not performed by the new Data Management API in this milestone.
