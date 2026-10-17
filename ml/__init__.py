"""TRACE training code (dataset generation, decoder training, adversarial loop).

Holds only ``fetch_models.py`` so far: the one place allowed to download (the
pinned NLI models). Training code arrives in M8-M10. Never imported by
``service``; the service loads a versioned model artefact by path or registry
id only.
"""
