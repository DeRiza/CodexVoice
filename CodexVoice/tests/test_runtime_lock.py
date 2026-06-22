from codexvoice.runtime_lock import SingleInstanceLock


def test_single_instance_lock_blocks_second_holder(tmp_path) -> None:
    path = tmp_path / "codexvoice.lock"
    first = SingleInstanceLock(path)
    second = SingleInstanceLock(path)

    try:
        assert first.acquire() is True
        assert second.acquire() is False
    finally:
        first.release()
        second.release()


def test_single_instance_lock_releases(tmp_path) -> None:
    path = tmp_path / "codexvoice.lock"
    first = SingleInstanceLock(path)
    second = SingleInstanceLock(path)

    assert first.acquire() is True
    first.release()
    assert second.acquire() is True
    second.release()

