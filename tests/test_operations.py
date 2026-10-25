import tempfile
import unittest
from pathlib import Path
from backend.app import Application
from backend.contracts import Error
from backend.db import put, get
from scripts.backup import backup, verify


class OperationsTests(unittest.TestCase):
    def test_backup_can_be_restored_and_cannot_overwrite(self):
        with tempfile.TemporaryDirectory() as directory:
            source = Path(directory) / "source.sqlite3"
            app = Application(source)
            try:
                with app.db.transaction(True) as c:
                    put(c, "work_items", {"id": "proof", "title": "Durable data"})
                destination = Path(directory) / "backup.sqlite3"
                backup(source, destination)
                self.assertEqual(verify(destination), 1)
                with self.assertRaises(FileExistsError):
                    backup(source, destination)
                restored = Application(destination)
                try:
                    with restored.db.transaction() as c:
                        self.assertEqual(
                            get(c, "work_items", "proof")["title"], "Durable data"
                        )
                finally:
                    restored.close()
            finally:
                app.close()

    def test_second_worker_cannot_recover_same_database(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "shared.sqlite3"
            first, second = Application(path), Application(path)
            try:
                first.runtime.launch()
                with self.assertRaises(Error) as error:
                    second.runtime.launch()
                self.assertEqual(error.exception.code, "worker_conflict")
            finally:
                first.close()
                second.close()
