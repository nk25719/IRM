from app.models.foundation import DataValidationError, ImportBatch, ImportRow
from app.services.base import BaseCrudService


class ImportBatchService(BaseCrudService[ImportBatch]):
    model = ImportBatch


class ImportRowService(BaseCrudService[ImportRow]):
    model = ImportRow


class DataValidationErrorService(BaseCrudService[DataValidationError]):
    model = DataValidationError
