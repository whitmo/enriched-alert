import pytest


@pytest.fixture(params=["asyncio"])
def anyio_backend(request):
    """Force anyio to use asyncio only (trio is not installed)."""
    return request.param
