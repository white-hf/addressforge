from __future__ import annotations

import unittest
from unittest.mock import patch

from addressforge.api.server import AddressPlatformService


class DummyModelService:
    pass


class TestAddressPlatformLazyRetrieval(unittest.TestCase):
    def test_vector_engine_is_not_loaded_eagerly(self):
        with patch("addressforge.api.server.get_vector_engine") as mocked_get_vector_engine:
            service = AddressPlatformService(model_service=DummyModelService())
            self.assertIsNone(service._vector_engine)
            mocked_get_vector_engine.assert_not_called()


if __name__ == "__main__":
    unittest.main()
