import unittest

from app.app import application


class TestChirpstackApp(unittest.TestCase):
    def setUp(self):
        self.app = application.test_client()
        self.app.testing = True

    def test_check_auth(self):
        response = self.app.get("/check-auth")
        assert response.status_code == 200
        assert "authenticated" in response.json

    def test_invalid_route(self):
        response = self.app.get("/nonexistent")
        assert response.status_code == 404


if __name__ == "__main__":
    unittest.main()
