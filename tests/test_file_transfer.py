"""
Unit tests for AeroGhost Chunked File Transfer & Verification
"""

import os
from core.file_transfer import OutgoingFileTransfer, IncomingFileTransfer, FileTransferState


def test_file_transfer_workflow(tmp_path):
    # Create sample dummy file
    source_file = tmp_path / "sample_doc.pdf"
    content = b"AeroGhost Secure Bluetooth File Transfer Payload " * 500  # ~25 KB
    source_file.write_bytes(content)

    outgoing = OutgoingFileTransfer(str(source_file), sender_nickname="Alice")
    assert outgoing.filesize == len(content)
    assert outgoing.total_chunks >= 1
    assert len(outgoing.sha256) == 64

    offer = outgoing.create_offer_packet()
    download_dir = str(tmp_path / "downloads")

    incoming = IncomingFileTransfer(offer, download_dir=download_dir)
    assert incoming.filesize == len(content)
    assert incoming.progress_percent == 0.0

    # Stream chunks from outgoing to incoming
    for i in range(outgoing.total_chunks):
        chunk_data = outgoing.read_chunk(i)
        assert chunk_data is not None
        incoming.write_chunk(i, chunk_data)

    assert incoming.is_complete() is True
    assert incoming.progress_percent == 100.0

    # Finalize and verify SHA-256
    verified = incoming.finalize()
    assert verified is True
    assert incoming.state == FileTransferState.COMPLETED
    assert os.path.exists(incoming.final_path)

    # Verify content match
    with open(incoming.final_path, "rb") as f:
        received_bytes = f.read()
    assert received_bytes == content
