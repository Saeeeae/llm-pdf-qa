from rag_pipeline.pipeline.parser import ParseBlock, _link_image_blocks_to_captions


def test_link_image_blocks_to_captions_enriches_image_text():
    blocks = [
        ParseBlock(block_type="caption", source_text="Figure 1. EGFR summary", page_number=2),
        ParseBlock(block_type="image", source_text="Extracted image 1 from page 2", page_number=2, metadata={"image_index": 1}),
    ]

    _link_image_blocks_to_captions(blocks)

    image_block = blocks[1]
    assert image_block.parent_local_idx == 0
    assert "Figure 1. EGFR summary" in image_block.source_text
    assert image_block.metadata["caption_text"] == "Figure 1. EGFR summary"
