# tests/helpers/mask_generator.py
from typing import Any, get_args, get_origin

from pydantic import BaseModel

from .exclusions import EXCLUSION_REGISTRY


def _mask_for_list(args: tuple[Any, ...]) -> dict[str, Any] | None:
    """Return a Pydantic __all__ exclude mask when args[0] is a BaseModel subclass."""
    if not args:
        return None
    item_cls = args[0]
    if not (isinstance(item_cls, type) and issubclass(item_cls, BaseModel)):
        return None
    nested = build_exclude_mask(item_cls)
    return {"__all__": nested} if nested else None


def _mask_for_model(annotation: Any) -> dict[str, Any] | None:
    """Return a nested exclude mask when annotation is a plain BaseModel subclass."""
    if not (isinstance(annotation, type) and issubclass(annotation, BaseModel)):
        return None
    return build_exclude_mask(annotation) or None


def _mask_for_union(args: tuple[Any, ...]) -> dict[str, Any] | None:
    """Return a nested exclude mask for the first BaseModel subclass found in args."""
    target = next(
        (a for a in args if isinstance(a, type) and issubclass(a, BaseModel)),
        None,
    )
    if target is None:
        return None
    return build_exclude_mask(target) or None


def _field_mask(annotation: Any, origin: Any, args: tuple[Any, ...]) -> dict[str, Any] | None:
    """Dispatch an annotation to the appropriate mask builder."""
    if origin is list:
        return _mask_for_list(args)
    if isinstance(annotation, type) and issubclass(annotation, BaseModel):
        return _mask_for_model(annotation)
    return _mask_for_union(args)


def build_exclude_mask(model_cls: type[BaseModel]) -> dict[str, Any]:
    """Build a Pydantic model_dump exclude dict for model_cls.

    Reads EXCLUSION_REGISTRY first (flat sets or pre-built nested dicts), then
    walks model_fields to auto-detect BaseModel-typed fields and emit the correct
    nested or __all__ exclusion structure.
    """
    registered = EXCLUSION_REGISTRY.get(model_cls.__name__, set())

    # Registry entry may be a flat set of field names (exclude those fields
    # entirely) or a pre-built nested dict (used for generic models whose
    # TypeVar annotations cannot be walked at introspection time).
    if isinstance(registered, dict):
        mask: dict[str, Any] = dict(registered)
    else:
        mask = dict.fromkeys(registered, True)

    for field_name, field_info in model_cls.model_fields.items():
        if field_name in mask:
            # Already covered by the registry entry; don't overwrite.
            continue
        annotation = field_info.annotation
        if not annotation:
            continue
        nested = _field_mask(annotation, get_origin(annotation), get_args(annotation))
        if nested:
            mask[field_name] = nested

    return mask
