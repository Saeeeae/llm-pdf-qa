from app.pipeline.lock import acquire, release


def test_acquire_success(fake_redis):
    assert acquire("doc1.pdf", "owner-A") is True


def test_acquire_duplicate_rejected(fake_redis):
    assert acquire("doc1.pdf", "owner-A") is True
    assert acquire("doc1.pdf", "owner-B") is False


def test_release_by_owner(fake_redis):
    acquire("doc1.pdf", "owner-A")
    release("doc1.pdf", "owner-A")
    # After release, another owner can acquire
    assert acquire("doc1.pdf", "owner-B") is True


def test_release_wrong_owner_no_op(fake_redis):
    acquire("doc1.pdf", "owner-A")
    release("doc1.pdf", "owner-WRONG")
    # Lock still held by owner-A
    assert acquire("doc1.pdf", "owner-B") is False


def test_different_docs_independent(fake_redis):
    assert acquire("doc1.pdf", "owner-A") is True
    assert acquire("doc2.pdf", "owner-A") is True
