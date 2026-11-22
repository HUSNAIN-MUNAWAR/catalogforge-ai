# Animation assets

`catalogforge-intake-reel.html` is generated from the repository’s real deterministic intake and validation functions. The JSON beside the storyboard is the machine-readable manifest for the reel.

Regenerate after changing intake, extraction, duplicate, or publishing behavior:

```bash
py -3.12 scripts/generate_animation_sequence.py
```

The HTML is self-contained and can be copied into a product walkthrough without adding a runtime dependency.
