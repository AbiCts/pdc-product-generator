"""Compact Oracle BRM/PDC 15.2 pricing XML generator."""

from __future__ import annotations

import json
import os
import uuid
import xml.etree.ElementTree as ET
from decimal import Decimal
from decimal import InvalidOperation
from pathlib import Path
from typing import Any

from neuro_san.interfaces.coded_tool import CodedTool


PDC_NS = "http://xmlns.oracle.com/communications/platform/model/pricing"
ROOT_TAG = f"{{{PDC_NS}}}PricingObjectsJXB"

ET.register_namespace("pdc", PDC_NS)

SCHEMA_PROFILE = "ORACLE_PDC_15_2"

COMPONENT_TYPES = {
    "ONE_TIME",
    "RECURRING",
    "USAGE",
}

IMPACT_TYPES = {
    "CHARGE",
    "GRANT",
}

OFFER_TYPES = {
    "ITEM",
    "SUBSCRIPTION",
    "SYSTEM",
}

QUANTITIES = {
    "ORIGINAL",
    "REMAINING",
}

TAX_TIMES = {
    "NONE",
    "BILLING_TIME",
    "DYNAMIC",
    "EVENT_TIME",
    "TAX_INCLUDED",
}

PRORATION_VALUES = {
    "FULL_CHARGE",
    "PRORATE_CHARGE",
    "NO_CHARGE",
}

DATE_RANGE_IMPACT_TYPES = {
    "EVENT_DATE",
    "PURCHASE_DATE",
    "INSTANTIATED_DATE",
}

VALIDITY_ROUNDING_VALUES = {
    "OFF",
    "ON",
    "NOT_SET",
}

SCALE_ROUNDING_VALUES = {
    "OFF",
    "ON",
}


def _missing(value: Any) -> bool:
    return value is None or value == ""


def _clean(value: Any) -> Any:
    if isinstance(value, str):
        return value.strip()

    if isinstance(value, list):
        return [_clean(item) for item in value]

    if isinstance(value, dict):
        return {
            str(key): _clean(item)
            for key, item in value.items()
        }

    return value


def _decimal(
    value: Any,
    field: str,
    errors: list[str],
) -> Decimal | None:
    if _missing(value):
        return None

    try:
        return Decimal(str(value))
    except (InvalidOperation, ValueError, TypeError):
        errors.append(f"{field} must be numeric.")
        return None


def _decimal_text(value: Decimal) -> str:
    text = format(value, "f")

    if "." in text:
        text = text.rstrip("0").rstrip(".")

    return text or "0"


def _bool(value: Any, default: bool = False) -> str:
    if value is None:
        value = default

    if isinstance(value, str):
        return (
            "true"
            if value.strip().lower() in {"true", "1", "yes", "y"}
            else "false"
        )

    return "true" if bool(value) else "false"


def _add(
    parent: ET.Element,
    name: str,
    value: Any | None = None,
) -> ET.Element:
    element = ET.SubElement(parent, name)

    if value is not None:
        element.text = str(value)

    return element


def _optional(
    parent: ET.Element,
    name: str,
    value: Any,
) -> None:
    if not _missing(value):
        _add(parent, name, value)


def _text(
    parent: ET.Element,
    name: str,
) -> str | None:
    element = parent.find(name)

    if element is None or element.text is None:
        return None

    return element.text.strip()


def _require(
    value: Any,
    path: str,
    question: str,
    questions: list[str],
) -> None:
    if _missing(value):
        questions.append(f"{path}: {question}")


def _unique(values: list[str]) -> list[str]:
    return list(dict.fromkeys(values))


def _apply_defaults(spec: dict[str, Any]) -> None:
    spec.setdefault("schema_profile", SCHEMA_PROFILE)
    spec.setdefault("characteristics", [])

    offer = spec.setdefault("offer", {})

    if isinstance(offer, dict):
        offer.setdefault("time_range", "0/inf")
        offer.setdefault("partial", False)
        offer.setdefault("purchase_min", -1.0)
        offer.setdefault("purchase_max", -1.0)
        offer.setdefault("own_min", -1.0)
        offer.setdefault("own_max", -1.0)
        offer.setdefault("expiry_notification", True)
        offer.setdefault("subscription_due_notification", True)
        offer.setdefault("post_expiry_notification", True)
        offer.setdefault("post_subscription_due_notification", True)
        offer.setdefault("date_range_impact_type", "EVENT_DATE")
        offer.setdefault("group_sharing_enabled", False)
        offer.setdefault("validity_rounding", "NOT_SET")
        offer.setdefault("scale_rounding", "OFF")

    bundle = spec.setdefault("bundle", {})

    if isinstance(bundle, dict):
        bundle.setdefault("enabled", False)
        bundle.setdefault("name", None)
        bundle.setdefault("description", None)
        bundle.setdefault("time_range", "0/inf")
        bundle.setdefault("items", [])


def _normalize_enums(spec: dict[str, Any]) -> None:
    spec["schema_profile"] = str(
        spec.get("schema_profile", SCHEMA_PROFILE)
    ).upper()

    offer = spec.get("offer", {})

    if isinstance(offer, dict):
        for field in (
            "offer_type",
            "applicable_quantity",
            "date_range_impact_type",
            "validity_rounding",
            "scale_rounding",
        ):
            if not _missing(offer.get(field)):
                offer[field] = str(offer[field]).upper()

    components = spec.get("components", [])

    if not isinstance(components, list):
        return

    for component in components:
        if not isinstance(component, dict):
            continue

        for field in (
            "type",
            "impact",
            "applicable_quantity",
            "tax_time",
        ):
            if not _missing(component.get(field)):
                component[field] = str(component[field]).upper()

        proration = component.get("proration")

        if isinstance(proration, dict):
            for field in ("first", "last", "cycle"):
                if not _missing(proration.get(field)):
                    proration[field] = str(
                        proration[field]
                    ).upper()


def _validate_characteristics(
    spec: dict[str, Any],
    questions: list[str],
    errors: list[str],
) -> None:
    characteristics = spec.get("characteristics", [])

    if not isinstance(characteristics, list):
        errors.append("characteristics must be a list.")
        return

    names: set[str] = set()

    for index, characteristic in enumerate(characteristics):
        prefix = f"characteristics[{index}]"

        if not isinstance(characteristic, dict):
            errors.append(f"{prefix} must be an object.")
            continue

        _require(
            characteristic.get("name"),
            f"{prefix}.name",
            "Provide the exact characteristic name.",
            questions,
        )

        _require(
            characteristic.get("value"),
            f"{prefix}.value",
            "Provide a value or omit the characteristic.",
            questions,
        )

        name = characteristic.get("name")

        if name:
            if name in names:
                errors.append(
                    f"Duplicate characteristic name: {name}."
                )

            if len(str(name)) > 255:
                errors.append(
                    f"{prefix}.name exceeds 255 characters."
                )

            names.add(str(name))


def _validate_offer(
    spec: dict[str, Any],
    questions: list[str],
    errors: list[str],
) -> dict[str, Any]:
    offer = spec.get("offer")

    if not isinstance(offer, dict):
        questions.append(
            "offer: Provide the charge-offering settings."
        )
        offer = {}
        spec["offer"] = offer

    required = {
        "payment_mode": "Provide the approved payment mode.",
        "offer_type": "Provide ITEM, SUBSCRIPTION, or SYSTEM.",
        "priority": "Provide the offering priority.",
        "applicable_quantity": "Provide ORIGINAL or REMAINING.",
        "purchase_cycle_dom": (
            "Provide the purchase-cycle day-of-month value."
        ),
    }

    for field, question in required.items():
        _require(
            offer.get(field),
            f"offer.{field}",
            question,
            questions,
        )

    offer_type = offer.get("offer_type")

    if offer_type and offer_type not in OFFER_TYPES:
        errors.append(
            "offer.offer_type must be ITEM, SUBSCRIPTION, or SYSTEM."
        )

    applicable_quantity = offer.get("applicable_quantity")

    if (
        applicable_quantity
        and applicable_quantity not in QUANTITIES
    ):
        errors.append(
            "offer.applicable_quantity must be ORIGINAL or REMAINING."
        )

    date_range_impact_type = offer.get(
        "date_range_impact_type"
    )

    if (
        date_range_impact_type
        and date_range_impact_type
        not in DATE_RANGE_IMPACT_TYPES
    ):
        errors.append(
            "offer.date_range_impact_type is unsupported."
        )

    validity_rounding = offer.get("validity_rounding")

    if (
        validity_rounding
        and validity_rounding not in VALIDITY_ROUNDING_VALUES
    ):
        errors.append(
            "offer.validity_rounding must be OFF, ON, or NOT_SET."
        )

    scale_rounding = offer.get("scale_rounding")

    if (
        scale_rounding
        and scale_rounding not in SCALE_ROUNDING_VALUES
    ):
        errors.append(
            "offer.scale_rounding must be OFF or ON."
        )

    priority = _decimal(
        offer.get("priority"),
        "offer.priority",
        errors,
    )

    if priority is not None and priority < 0:
        errors.append(
            "offer.priority cannot be negative."
        )

    for field in (
        "purchase_min",
        "purchase_max",
        "own_min",
        "own_max",
    ):
        value = _decimal(
            offer.get(field),
            f"offer.{field}",
            errors,
        )

        if value is not None:
            offer[field] = _decimal_text(value)

    return offer


def _validate_usage_tiers(
    component: dict[str, Any],
    prefix: str,
    impact: str | None,
    questions: list[str],
    errors: list[str],
) -> None:
    tiers = component.get("tiers")

    if not isinstance(tiers, list) or not tiers:
        questions.append(
            f"{prefix}.tiers: Provide at least one usage tier."
        )
        return

    previous_upper: Decimal | None = None
    open_ended_seen = False

    for index, tier in enumerate(tiers):
        tier_prefix = f"{prefix}.tiers[{index}]"

        if not isinstance(tier, dict):
            errors.append(
                f"{tier_prefix} must be an object."
            )
            continue

        for field in (
            "lower_bound",
            "upper_bound",
            "amount",
        ):
            _require(
                tier.get(field),
                f"{tier_prefix}.{field}",
                f"Provide {field.replace('_', ' ')}.",
                questions,
            )

        amount = _decimal(
            tier.get("amount"),
            f"{tier_prefix}.amount",
            errors,
        )

        if amount is not None:
            if impact == "CHARGE" and amount < 0:
                errors.append(
                    f"{tier_prefix}.amount cannot be negative "
                    "for a CHARGE."
                )

            if impact == "GRANT" and amount >= 0:
                errors.append(
                    f"{tier_prefix}.amount must be negative "
                    "for a GRANT."
                )

            tier["amount"] = _decimal_text(amount)

        lower_raw = tier.get("lower_bound")
        upper_raw = tier.get("upper_bound")

        lower: Decimal | None = None
        upper: Decimal | None = None

        if str(lower_raw).upper() not in {
            "NO_MIN",
            "-INF",
        }:
            lower = _decimal(
                lower_raw,
                f"{tier_prefix}.lower_bound",
                errors,
            )

        if str(upper_raw).upper() in {
            "NO_MAX",
            "INF",
        }:
            open_ended_seen = True
        else:
            upper = _decimal(
                upper_raw,
                f"{tier_prefix}.upper_bound",
                errors,
            )

        if open_ended_seen and index < len(tiers) - 1:
            errors.append(
                f"{tier_prefix} is open-ended but is not the final tier."
            )

        if (
            lower is not None
            and upper is not None
            and lower >= upper
        ):
            errors.append(
                f"{tier_prefix}.lower_bound must be less than "
                "upper_bound."
            )

        if (
            previous_upper is not None
            and lower is not None
            and lower < previous_upper
        ):
            errors.append(
                f"{tier_prefix} overlaps the previous tier."
            )

        if upper is not None:
            previous_upper = upper


def _validate_component(
    component: dict[str, Any],
    index: int,
    questions: list[str],
    errors: list[str],
) -> None:
    prefix = f"components[{index}]"

    required = {
        "name": "Provide a unique component name.",
        "type": "Provide ONE_TIME, RECURRING, or USAGE.",
        "impact": "Provide CHARGE or GRANT.",
        "event_name": "Provide the exact catalog event name.",
        "rum_name": "Provide the exact catalog RUM.",
        "currency_code": "Provide the subscriber currency code.",
        "balance_element_num_code": (
            "Provide the exact balance-element code."
        ),
        "unit_of_measure": "Provide the PDC unit of measure.",
        "applicable_quantity": (
            "Provide ORIGINAL or REMAINING."
        ),
        "tax_time": "Provide NONE or an approved tax-time value.",
    }

    for field, question in required.items():
        _require(
            component.get(field),
            f"{prefix}.{field}",
            question,
            questions,
        )

    component_type = component.get("type")
    impact = component.get("impact")

    if (
        component_type
        and component_type not in COMPONENT_TYPES
    ):
        errors.append(
            f"{prefix}.type must be ONE_TIME, RECURRING, or USAGE."
        )

    if impact and impact not in IMPACT_TYPES:
        errors.append(
            f"{prefix}.impact must be CHARGE or GRANT."
        )

    if (
        component.get("applicable_quantity")
        and component["applicable_quantity"] not in QUANTITIES
    ):
        errors.append(
            f"{prefix}.applicable_quantity must be "
            "ORIGINAL or REMAINING."
        )

    if (
        component.get("tax_time")
        and component["tax_time"] not in TAX_TIMES
    ):
        errors.append(
            f"{prefix}.tax_time has an unsupported value."
        )

    if (
        component.get("tax_time")
        and component["tax_time"] != "NONE"
    ):
        _require(
            component.get("tax_code"),
            f"{prefix}.tax_code",
            "Provide the exact tax code.",
            questions,
        )

    validity = component.get("validity")

    if not isinstance(validity, dict):
        questions.append(
            f"{prefix}.validity: Provide validity settings."
        )
        validity = {}
        component["validity"] = validity

    for field in (
        "absolute_start",
        "absolute_end",
        "start_mode",
        "end_mode",
        "range",
    ):
        _require(
            validity.get(field),
            f"{prefix}.validity.{field}",
            f"Provide {field.replace('_', ' ')}.",
            questions,
        )

    if component_type == "USAGE":
        _validate_usage_tiers(
            component,
            prefix,
            impact,
            questions,
            errors,
        )
    else:
        _require(
            component.get("amount"),
            f"{prefix}.amount",
            "Provide the exact charge or grant amount.",
            questions,
        )

        amount = _decimal(
            component.get("amount"),
            f"{prefix}.amount",
            errors,
        )

        if amount is not None:
            if impact == "CHARGE" and amount < 0:
                errors.append(
                    f"{prefix}.amount cannot be negative "
                    "for a CHARGE."
                )

            if impact == "GRANT" and amount >= 0:
                errors.append(
                    f"{prefix}.amount must be negative "
                    "for a GRANT."
                )

            component["amount"] = _decimal_text(amount)

    if component_type == "RECURRING":
        proration = component.get("proration")

        if not isinstance(proration, dict):
            questions.append(
                f"{prefix}.proration: Provide first, last, "
                "and cycle rules."
            )
            return

        for field in ("first", "last", "cycle"):
            _require(
                proration.get(field),
                f"{prefix}.proration.{field}",
                f"Provide the {field} proration rule.",
                questions,
            )

            value = proration.get(field)

            if (
                not _missing(value)
                and value not in PRORATION_VALUES
            ):
                errors.append(
                    f"{prefix}.proration.{field} is unsupported."
                )


def _validate_offer_type_rules(
    spec: dict[str, Any],
    errors: list[str],
) -> None:
    offer = spec.get("offer", {})
    components = spec.get("components", [])

    if not isinstance(offer, dict):
        return

    if not isinstance(components, list):
        return

    offer_type = offer.get("offer_type")
    categories = [
        component.get("type")
        for component in components
        if isinstance(component, dict)
    ]

    if offer_type == "ITEM":
        if (
            len(categories) != 1
            or categories[0] != "ONE_TIME"
        ):
            errors.append(
                "ITEM offers must contain exactly one "
                "ONE_TIME charge."
            )

    if offer_type == "SYSTEM":
        invalid = [
            category
            for category in categories
            if category != "USAGE"
        ]

        if invalid:
            errors.append(
                "SYSTEM offers may contain only USAGE charges."
            )

    recurring_keys: set[tuple[str, str]] = set()

    for component in components:
        if not isinstance(component, dict):
            continue

        if component.get("type") != "RECURRING":
            continue

        key = (
            str(component.get("event_name", "")),
            str(component.get("impact", "")),
        )

        if key in recurring_keys:
            errors.append(
                "A charge offering cannot contain duplicate recurring "
                "charges with the same event and impact type."
            )

        recurring_keys.add(key)


def _validate_bundle(
    spec: dict[str, Any],
    questions: list[str],
    errors: list[str],
) -> None:
    bundle = spec.get("bundle", {})

    if not isinstance(bundle, dict):
        errors.append("bundle must be an object.")
        return

    if bundle.get("enabled") is not True:
        return

    _require(
        bundle.get("name"),
        "bundle.name",
        "Provide the bundle name.",
        questions,
    )

    _require(
        bundle.get("description"),
        "bundle.description",
        "Provide the bundle description.",
        questions,
    )

    items = bundle.get("items")

    if not isinstance(items, list) or not items:
        questions.append(
            "bundle.items: Provide at least one bundle item."
        )
        return

    allowed_offering = spec.get("name")

    for index, item in enumerate(items):
        prefix = f"bundle.items[{index}]"

        if not isinstance(item, dict):
            errors.append(f"{prefix} must be an object.")
            continue

        for field in (
            "charge_offering_name",
            "quantity",
            "purchase_mode",
            "renewal_mode",
        ):
            _require(
                item.get(field),
                f"{prefix}.{field}",
                f"Provide {field.replace('_', ' ')}.",
                questions,
            )

        offering_name = item.get("charge_offering_name")

        if (
            offering_name
            and offering_name != allowed_offering
        ):
            errors.append(
                f"{prefix} references an offering not generated "
                "by this specification."
            )


def _validate_spec(
    spec: dict[str, Any],
) -> tuple[list[str], list[str]]:
    questions: list[str] = []
    errors: list[str] = []

    _apply_defaults(spec)
    _normalize_enums(spec)

    if spec.get("schema_profile") != SCHEMA_PROFILE:
        errors.append(
            "schema_profile must be ORACLE_PDC_15_2."
        )

    _require(
        spec.get("name"),
        "name",
        "Provide the charge-offering name.",
        questions,
    )

    _require(
        spec.get("description"),
        "description",
        "Provide a description.",
        questions,
    )

    _require(
        spec.get("price_list_name"),
        "price_list_name",
        "Provide the exact existing PDC price-list name.",
        questions,
    )

    _require(
        spec.get("product_spec_name"),
        "product_spec_name",
        "Provide the exact existing PDC product-specification name.",
        questions,
    )

    if len(str(spec.get("name", ""))) > 255:
        errors.append(
            "name exceeds Oracle's 255-character limit."
        )

    if len(str(spec.get("description", ""))) > 255:
        errors.append(
            "description exceeds Oracle's 255-character limit."
        )

    _validate_characteristics(
        spec,
        questions,
        errors,
    )

    _validate_offer(
        spec,
        questions,
        errors,
    )

    components = spec.get("components")

    if not isinstance(components, list) or not components:
        questions.append(
            "components: Provide at least one charge or grant component."
        )
        return _unique(questions), errors

    names: set[str] = set()

    for index, component in enumerate(components):
        if not isinstance(component, dict):
            errors.append(
                f"components[{index}] must be an object."
            )
            continue

        _validate_component(
            component,
            index,
            questions,
            errors,
        )

        name = component.get("name")

        if name:
            if name in names:
                errors.append(
                    f"Duplicate component name: {name}."
                )

            names.add(str(name))

    _validate_offer_type_rules(spec, errors)
    _validate_bundle(spec, questions, errors)

    return _unique(questions), errors


def _load_catalog_profile(
) -> tuple[dict[str, Any] | None, list[str]]:
    warnings: list[str] = []
    path_value = os.getenv("PDC_CATALOG_PROFILE")

    if not path_value:
        warnings.append(
            "No PDC catalog profile was configured; product "
            "specification, characteristic, event, RUM, and balance "
            "element existence were not catalog-validated."
        )
        return None, warnings

    path = Path(path_value).expanduser().resolve()

    if not path.is_file():
        warnings.append(
            f"PDC catalog profile was not found: {path}."
        )
        return None, warnings

    try:
        with path.open(
            "r",
            encoding="utf-8",
        ) as profile_file:
            profile = json.load(profile_file)
    except (OSError, json.JSONDecodeError) as exc:
        warnings.append(
            f"PDC catalog profile could not be loaded: {exc}."
        )
        return None, warnings

    if not isinstance(profile, dict):
        warnings.append(
            "PDC catalog profile must contain a JSON object."
        )
        return None, warnings

    return profile, warnings


def _validate_catalog(
    spec: dict[str, Any],
    profile: dict[str, Any] | None,
) -> tuple[list[str], bool]:
    if profile is None:
        return [], False

    errors: list[str] = []
    product_specs = profile.get("product_specs", {})
    balance_elements = profile.get("balance_elements", {})

    product_spec_name = spec["product_spec_name"]
    product_spec = product_specs.get(product_spec_name)

    if not isinstance(product_spec, dict):
        errors.append(
            f"Catalog profile does not contain product specification "
            f"{product_spec_name}."
        )
        return errors, False

    allowed_characteristics = set(
        product_spec.get("characteristics", [])
    )

    for characteristic in spec.get("characteristics", []):
        name = characteristic.get("name")

        if (
            allowed_characteristics
            and name not in allowed_characteristics
        ):
            errors.append(
                f"Characteristic {name} is not approved for "
                f"{product_spec_name}."
            )

    service_event_map = product_spec.get(
        "service_event_map",
        []
    )

    approved_events: dict[str, set[str]] = {}

    for mapping in service_event_map:
        if not isinstance(mapping, dict):
            continue

        event = mapping.get("event")
        rums = mapping.get("rums", [])

        if event:
            approved_events[str(event)] = {
                str(rum)
                for rum in rums
            }

    for index, component in enumerate(spec["components"]):
        event_name = component["event_name"]
        rum_name = component["rum_name"]

        if event_name not in approved_events:
            errors.append(
                f"components[{index}].event_name is not approved "
                f"for {product_spec_name}."
            )
        elif rum_name not in approved_events[event_name]:
            errors.append(
                f"components[{index}].rum_name is not approved "
                f"for event {event_name}."
            )

        code = str(
            component["balance_element_num_code"]
        )

        balance = balance_elements.get(code)

        if not isinstance(balance, dict):
            errors.append(
                f"Balance element {code} is not present in the "
                "catalog profile."
            )
            continue

        expected_currency = balance.get("currency")

        if (
            expected_currency
            and expected_currency
            != component["currency_code"]
        ):
            errors.append(
                f"Balance element {code} is configured for "
                f"{expected_currency}, not "
                f"{component['currency_code']}."
            )

    return errors, not errors


def _price_validity(
    parent: ET.Element,
    validity: dict[str, Any],
) -> None:
    node = _add(parent, "priceValidity")

    _add(
        node,
        "startValidityMode",
        validity["start_mode"],
    )

    _add(
        node,
        "endValidityMode",
        validity["end_mode"],
    )

    _add(
        node,
        "validityRange",
        validity["range"],
    )

    _optional(
        node,
        "relativeStartOffset",
        validity.get("relative_start_offset"),
    )

    _optional(
        node,
        "relativeStartOffsetUnit",
        validity.get("relative_start_offset_unit"),
    )

    _optional(
        node,
        "relativeEndOffset",
        validity.get("relative_end_offset"),
    )

    _optional(
        node,
        "relativeEndOffsetUnit",
        validity.get("relative_end_offset_unit"),
    )


def _charge(
    parent: ET.Element,
    component: dict[str, Any],
    amount: Any,
    tag: str,
) -> None:
    node = _add(parent, tag)

    _add(node, "price", amount)
    _add(
        node,
        "unitOfMeasure",
        component["unit_of_measure"],
    )
    _add(
        node,
        "balanceElementNumCode",
        component["balance_element_num_code"],
    )
    _add(
        node,
        "discountable",
        _bool(component.get("discountable"), True),
    )
    _add(node, "priceType", component["impact"])

    _price_validity(
        node,
        component["validity"],
    )

    if tag in {
        "oneTimeCharge",
        "recurringCharge",
    }:
        _add(
            node,
            "proratable",
            _bool(component.get("proratable"), True),
        )

    _add(
        node,
        "impactType",
        component.get("impact_type", "SCALED"),
    )

    _optional(
        node,
        "taxCode",
        component.get("tax_code"),
    )


def _tier(
    model: ET.Element,
    component: dict[str, Any],
    tier: dict[str, Any],
) -> None:
    component_type = component["type"]
    price_tier = _add(model, "priceTier")

    _add(
        price_tier,
        "lowerBound",
        tier.get("lower_bound", "NO_MIN"),
    )

    basis = _add(price_tier, "tierBasis")
    _add(basis, "rumTierExpression")

    _add(
        price_tier,
        "rumName",
        component["rum_name"],
    )

    _add(
        price_tier,
        "enforceCreditLimit",
        component.get(
            "enforce_credit_limit",
            "NORMAL",
        ),
    )

    if component_type == "USAGE":
        _add(
            price_tier,
            "distributionMethod",
            component.get(
                "distribution_method",
                "NONE",
            ),
        )

        period = _add(
            price_tier,
            "priceTierValidityPeriod",
        )

        _add(
            period,
            "validityRange",
            component["validity"]["range"],
        )

        tier_range = _add(
            period,
            "priceTierRange",
        )

        _add(
            tier_range,
            "upperBound",
            tier["upper_bound"],
        )

        _charge(
            tier_range,
            component,
            tier["amount"],
            "scaledCharge",
        )
        return

    tier_range = _add(
        price_tier,
        "tierRange",
    )

    _add(
        tier_range,
        "upperBound",
        tier.get("upper_bound", "NO_MAX"),
    )

    tag = (
        "oneTimeCharge"
        if component_type == "ONE_TIME"
        else "recurringCharge"
    )

    _charge(
        tier_range,
        component,
        tier.get("amount", component["amount"]),
        tag,
    )


def _rate_plan(
    root: ET.Element,
    spec: dict[str, Any],
    component: dict[str, Any],
) -> None:
    node = _add(root, "chargeRatePlan")

    _add(node, "name", component["rate_plan_name"])
    _add(node, "internalId", component["rate_plan_id"])

    _add(
        node,
        "pricingProfileName",
        (
            "Convergent Usage"
            if component["type"] == "USAGE"
            else "Subscription"
        ),
    )

    _add(
        node,
        "priceListName",
        spec["price_list_name"],
    )

    _add(node, "obsolete", "false")
    _add(node, "applicableRums", component["rum_name"])

    _add(
        node,
        "applicableQuantity",
        component["applicable_quantity"],
    )

    _add(node, "taxTime", component["tax_time"])

    _optional(
        node,
        "taxCode",
        component.get("tax_code"),
    )

    _add(
        node,
        "todMode",
        component.get("tod_mode", "START_TIME"),
    )

    _add(
        node,
        "applicableQtyTreatment",
        component.get(
            "applicable_qty_treatment",
            "CONTINUOUS",
        ),
    )

    _add(node, "permittedName", spec["product_spec_name"])
    _add(node, "permittedType", "PRODUCT")
    _add(node, "eventName", component["event_name"])

    _add(
        node,
        "cycleFeeFlag",
        component.get("cycle_fee_flag", 0),
    )

    _add(
        node,
        "billOffset",
        component.get("bill_offset", 0),
    )

    currency = _add(node, "subscriberCurrency")

    _add(
        currency,
        "currencyCode",
        component["currency_code"],
    )

    date_range = _add(
        currency,
        "crpRelDateRange",
    )

    absolute = _add(
        date_range,
        "absoluteDateRange",
    )

    _add(
        absolute,
        "startDate",
        component["validity"]["absolute_start"],
    )

    _add(
        absolute,
        "endDate",
        component["validity"]["absolute_end"],
    )

    composite = _add(
        date_range,
        "crpCompositePopModel",
    )

    model_tag = {
        "ONE_TIME": "oneTimePopModel",
        "RECURRING": "recurringPopModel",
        "USAGE": "usageChargePopModel",
    }[component["type"]]

    model = _add(composite, model_tag)

    tiers = component.get("tiers")

    if not tiers:
        tiers = [
            {
                "lower_bound": "NO_MIN",
                "upper_bound": "NO_MAX",
                "amount": component["amount"],
            }
        ]

    for tier in tiers:
        _tier(model, component, tier)


def _event_map(
    offering: ET.Element,
    component: dict[str, Any],
) -> None:
    node = _add(offering, "chargeEventMap")

    _add(node, "eventName", component["event_name"])
    _add(node, "validIfCancelled", "false")
    _add(node, "validIfInactive", "false")
    _add(node, "validIfSuspendedActive", "false")

    _add(
        node,
        "timezoneMode",
        component.get("timezone_mode", "EVENT"),
    )

    _add(
        node,
        "minQuantity",
        component.get("min_quantity", 0),
    )

    _add(
        node,
        "minQuantityUnit",
        component.get("min_quantity_unit", "NONE"),
    )

    _add(
        node,
        "incrementQuantity",
        component.get("increment_quantity", 1),
    )

    _add(
        node,
        "incrementQuantityUnit",
        component.get(
            "increment_quantity_unit",
            "NONE",
        ),
    )

    _add(
        node,
        "roundingMode",
        component.get("rounding_mode", "NEAREST"),
    )

    if component["type"] == "RECURRING":
        _add(
            node,
            "prorateFirst",
            component["proration"]["first"],
        )

        _add(
            node,
            "prorateLast",
            component["proration"]["last"],
        )

        _add(
            node,
            "prorateCycle",
            component["proration"]["cycle"],
        )

    info = _add(node, "chargeRatePlanInfo")
    _add(
        info,
        "targetEngine",
        component.get("target_engine", "RRE"),
    )

    _add(
        node,
        "chargeRatePlanName",
        component["rate_plan_name"],
    )

    _add(
        node,
        "ratePlanIID",
        component["rate_plan_id"],
    )


def _offering(
    root: ET.Element,
    spec: dict[str, Any],
) -> None:
    offer = spec["offer"]
    identifiers = spec["_ids"]

    node = ET.SubElement(
        root,
        "chargeOffering",
        {
            "externalID": identifiers["offering"],
        },
    )

    _add(node, "name", spec["name"])
    _add(node, "description", spec["description"])
    _add(node, "internalId", identifiers["offering"])

    _add(
        node,
        "pricingProfileName",
        "Product Offering",
    )

    _add(
        node,
        "priceListName",
        spec["price_list_name"],
    )

    _add(node, "obsolete", "false")

    _add(
        node,
        "timeRange",
        offer.get("time_range", "0/inf"),
    )

    _add(
        node,
        "productSpecName",
        spec["product_spec_name"],
    )

    for item in spec.get("characteristics", []):
        characteristic = _add(
            node,
            "productSpecCharacteristic",
        )

        _add(characteristic, "name", item["name"])
        _add(characteristic, "value", item["value"])

    _add(node, "offerType", offer["offer_type"])
    _add(node, "priority", offer["priority"])

    _add(
        node,
        "partial",
        _bool(offer.get("partial"), False),
    )

    _add(
        node,
        "purchaseMin",
        offer.get("purchase_min", -1.0),
    )

    _add(
        node,
        "purchaseMax",
        offer.get("purchase_max", -1.0),
    )

    _add(
        node,
        "ownMin",
        offer.get("own_min", -1.0),
    )

    _add(
        node,
        "ownMax",
        offer.get("own_max", -1.0),
    )

    _add(
        node,
        "applicableQuantity",
        offer["applicable_quantity"],
    )

    _add(
        node,
        "purchaseCycleDOM",
        offer["purchase_cycle_dom"],
    )

    _add(
        node,
        "expiryNotification",
        _bool(
            offer.get("expiry_notification"),
            True,
        ),
    )

    _add(
        node,
        "subscriptionDueNotification",
        _bool(
            offer.get("subscription_due_notification"),
            True,
        ),
    )

    _add(
        node,
        "postExpiryNotification",
        _bool(
            offer.get("post_expiry_notification"),
            True,
        ),
    )

    _add(
        node,
        "postSubscriptionDueNotification",
        _bool(
            offer.get("post_subscription_due_notification"),
            True,
        ),
    )

    _add(
        node,
        "dateRangeImpactType",
        offer.get(
            "date_range_impact_type",
            "EVENT_DATE",
        ),
    )

    _add(
        node,
        "groupSharingEnabled",
        _bool(
            offer.get("group_sharing_enabled"),
            False,
        ),
    )

    _add(
        node,
        "validityRounding",
        offer.get(
            "validity_rounding",
            "NOT_SET",
        ),
    )

    _add(
        node,
        "scaleRounding",
        offer.get("scale_rounding", "OFF"),
    )

    for component in spec["components"]:
        _event_map(node, component)


def _validity_block(
    parent: ET.Element,
    name: str,
    value: Any,
) -> None:
    node = _add(parent, name)

    if isinstance(value, dict):
        _add(node, "offset", value.get("offset", 0))
        _add(node, "mode", value["mode"])
    else:
        _add(node, "offset", 0)
        _add(node, "mode", value)


def _bundle(
    root: ET.Element,
    spec: dict[str, Any],
) -> None:
    bundle = spec.get("bundle", {})

    if bundle.get("enabled") is not True:
        return

    node = _add(root, "bundledProductOffering")

    _add(node, "name", bundle["name"])
    _add(node, "description", bundle["description"])
    _add(node, "internalId", spec["_ids"]["bundle"])

    _add(
        node,
        "pricingProfileName",
        "Product Offering",
    )

    _add(
        node,
        "priceListName",
        spec["price_list_name"],
    )

    _add(node, "obsolete", "false")

    _add(
        node,
        "timeRange",
        bundle.get("time_range", "0/inf"),
    )

    _add(
        node,
        "productSpecName",
        spec["product_spec_name"],
    )

    _add(
        node,
        "billOnPurchase",
        _bool(
            bundle.get("bill_on_purchase"),
            False,
        ),
    )

    _add(
        node,
        "firstUsageActivation",
        _bool(
            bundle.get("first_usage_activation"),
            False,
        ),
    )

    _add(
        node,
        "customize",
        bundle.get("customize", "OPTIONAL"),
    )

    _add(
        node,
        "groupBalanceElements",
        _bool(
            bundle.get("group_balance_elements"),
            False,
        ),
    )

    for item in bundle["items"]:
        child = _add(
            node,
            "bundledProductOfferingItem",
        )

        for xml_name, field in (
            ("purchaseStart", "purchase_start"),
            ("purchaseEnd", "purchase_end"),
            ("usageStart", "usage_start"),
            ("usageEnd", "usage_end"),
            ("cycleStart", "cycle_start"),
            ("cycleEnd", "cycle_end"),
        ):
            _validity_block(
                child,
                xml_name,
                item.get(
                    field,
                    {
                        "offset": 0,
                        "mode": "NOW_TO_NEVER",
                    },
                ),
            )

        _add(
            child,
            "status",
            item.get("status", 1),
        )

        _add(
            child,
            "statusCode",
            item.get("status_code", 0),
        )

        _add(
            child,
            "renewalMode",
            _bool(item["renewal_mode"]),
        )

        _add(child, "quantity", item["quantity"])

        _add(
            child,
            "purchaseChargeAdjustment",
            item.get(
                "purchase_charge_adjustment",
                0.0,
            ),
        )

        _add(
            child,
            "usageChargeAdjustment",
            item.get(
                "usage_charge_adjustment",
                0.0,
            ),
        )

        _add(
            child,
            "cycleChargeAdjustment",
            item.get(
                "cycle_charge_adjustment",
                0.0,
            ),
        )

        _add(
            child,
            "purchaseMode",
            item["purchase_mode"],
        )

        _add(
            child,
            "chargeOfferingName",
            item["charge_offering_name"],
        )


def _assign_ids(spec: dict[str, Any]) -> None:
    offering_id = str(uuid.uuid4())

    spec["_ids"] = {
        "offering": offering_id,
        "bundle": (
            str(uuid.uuid4())
            if spec.get("bundle", {}).get("enabled")
            else None
        ),
    }

    used_names: set[str] = set()

    for component in spec["components"]:
        rate_plan_name = component.get("rate_plan_name")

        if not rate_plan_name:
            rate_plan_name = (
                f"{spec['name']}_{component['name']}_Rate_Plan"
            )

        if rate_plan_name in used_names:
            raise ValueError(
                f"Duplicate rate-plan name: {rate_plan_name}."
            )

        used_names.add(rate_plan_name)
        component["rate_plan_name"] = rate_plan_name
        component["rate_plan_id"] = str(uuid.uuid4())


def _render(spec: dict[str, Any]) -> str:
    root = ET.Element(ROOT_TAG)

    for component in spec["components"]:
        _rate_plan(root, spec, component)

    _offering(root, spec)
    _bundle(root, spec)

    ET.indent(root, space="  ")

    body = ET.tostring(
        root,
        encoding="unicode",
        short_empty_elements=True,
    )

    return (
        '<?xml version="1.0" encoding="UTF-8"?>\n'
        + body
    )


def _validate_xml(
    xml: str,
    spec: dict[str, Any],
) -> list[str]:
    errors: list[str] = []

    upper_xml = xml.upper()

    if (
        "<!DOCTYPE" in upper_xml
        or "<!ENTITY" in upper_xml
    ):
        return [
            "DTD and entity declarations are forbidden."
        ]

    try:
        root = ET.fromstring(xml)
    except ET.ParseError as exc:
        return [
            f"Generated XML is not well formed: {exc}"
        ]

    if root.tag != ROOT_TAG:
        errors.append(
            "Incorrect PDC root element or namespace."
        )

    object_order = {
        "chargeRatePlan": 0,
        "chargeOffering": 1,
        "bundledProductOffering": 2,
    }

    previous = -1

    for child in root:
        name = child.tag.rsplit("}", 1)[-1]

        if name not in object_order:
            errors.append(
                f"Unsupported root object: {name}."
            )
            continue

        current = object_order[name]

        if current < previous:
            errors.append(
                "PDC pricing objects are in the wrong order."
            )

        previous = max(previous, current)

    rate_plans: dict[str, str] = {}
    used_ids: set[str] = set()

    for rate_plan in root.findall("chargeRatePlan"):
        name = _text(rate_plan, "name")
        internal_id = _text(
            rate_plan,
            "internalId",
        )

        if not name or not internal_id:
            errors.append(
                "A chargeRatePlan is missing its name "
                "or internalId."
            )
            continue

        if name in rate_plans:
            errors.append(
                f"Duplicate chargeRatePlan name: {name}."
            )

        if internal_id in used_ids:
            errors.append(
                f"Duplicate pricing-object ID: {internal_id}."
            )

        try:
            uuid.UUID(internal_id)
        except ValueError:
            errors.append(
                f"Invalid rate-plan UUID: {internal_id}."
            )

        rate_plans[name] = internal_id
        used_ids.add(internal_id)

    offerings = root.findall("chargeOffering")

    if len(offerings) != 1:
        errors.append(
            "Exactly one generated chargeOffering is required."
        )
    else:
        offering = offerings[0]
        offering_id = _text(
            offering,
            "internalId",
        )

        external_id = offering.attrib.get("externalID")

        if offering_id != external_id:
            errors.append(
                "chargeOffering externalID must equal "
                "its internalId."
            )

        if offering_id in used_ids:
            errors.append(
                "chargeOffering ID duplicates a rate-plan ID."
            )

        if offering_id:
            try:
                uuid.UUID(offering_id)
            except ValueError:
                errors.append(
                    f"Invalid offering UUID: {offering_id}."
                )

        for event_map in offering.findall(
            "chargeEventMap"
        ):
            name = _text(
                event_map,
                "chargeRatePlanName",
            )

            rate_plan_id = _text(
                event_map,
                "ratePlanIID",
            )

            if name not in rate_plans:
                errors.append(
                    "chargeEventMap references unknown "
                    f"rate plan: {name}."
                )
            elif rate_plans[name] != rate_plan_id:
                errors.append(
                    "ratePlanIID does not match "
                    f"rate plan {name}."
                )

    allowed_offerings = {
        spec["name"],
    }

    for bundle in root.findall(
        "bundledProductOffering"
    ):
        bundle_id = _text(bundle, "internalId")

        if bundle_id in used_ids:
            errors.append(
                "Bundle ID duplicates another pricing-object ID."
            )

        if bundle_id:
            try:
                uuid.UUID(bundle_id)
            except ValueError:
                errors.append(
                    f"Invalid bundle UUID: {bundle_id}."
                )

        for item in bundle.findall(
            "bundledProductOfferingItem"
        ):
            offering_name = _text(
                item,
                "chargeOfferingName",
            )

            if offering_name not in allowed_offerings:
                errors.append(
                    "Bundle references unknown charge offering: "
                    f"{offering_name}."
                )

    return errors


def _validate_xsd(
    xml: str,
) -> tuple[list[str], bool, list[str]]:
    xsd_path_value = os.getenv("PDC_PRICING_XSD_PATH")

    if not xsd_path_value:
        return (
            [],
            False,
            [
                "PDC_PRICING_XSD_PATH is not configured; "
                "Oracle installation XSD validation was skipped."
            ],
        )

    xsd_path = Path(
        xsd_path_value
    ).expanduser().resolve()

    if not xsd_path.is_file():
        return (
            [
                f"Oracle PDC XSD was not found: {xsd_path}."
            ],
            False,
            [],
        )

    try:
        from lxml import etree as LET
    except ImportError:
        return (
            [
                "lxml is required when "
                "PDC_PRICING_XSD_PATH is configured."
            ],
            False,
            [],
        )

    try:
        parser = LET.XMLParser(
            resolve_entities=False,
            no_network=True,
        )

        schema_document = LET.parse(
            str(xsd_path),
            parser,
        )

        schema = LET.XMLSchema(schema_document)

        document = LET.fromstring(
            xml.encode("utf-8"),
            parser,
        )

        if schema.validate(document):
            return [], True, []

        errors = [
            f"XSD line {entry.line}: {entry.message}"
            for entry in schema.error_log
        ]

        return errors, False, []

    except (LET.XMLSyntaxError, LET.XMLSchemaParseError) as exc:
        return (
            [f"Oracle PDC XSD validation failed: {exc}"],
            False,
            [],
        )


def _base_validation() -> dict[str, Any]:
    return {
        "profile": "Oracle PDC 15.2",
        "reference_validated": False,
        "documentation_rules_validated": False,
        "service_event_map_validated": False,
        "catalog_validated": False,
        "xsd_validated": False,
        "import_tested": False,
        "import_certified": False,
        "errors": [],
        "warnings": [],
    }


def _invalid_result(
    errors: list[str],
) -> dict[str, Any]:
    validation = _base_validation()
    validation["errors"] = errors

    return {
        "status": "invalid",
        "questions": [],
        "xml": None,
        "validation": validation,
    }


class PdcProductTool(CodedTool):
    """Validate, render, and verify a PDC product."""

    async def async_invoke(
        self,
        args: dict[str, Any],
        sly_data: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        return self.invoke(args, sly_data)

    def invoke(
        self,
        args: dict[str, Any],
        sly_data: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        del sly_data

        raw_spec = args.get("spec_json")

        if isinstance(raw_spec, dict):
            spec = _clean(raw_spec)

        elif isinstance(raw_spec, str):
            try:
                spec = _clean(
                    json.loads(raw_spec)
                )
            except json.JSONDecodeError as exc:
                return _invalid_result(
                    [
                        f"spec_json is invalid JSON: {exc}"
                    ]
                )

        else:
            return _invalid_result(
                [
                    "spec_json must contain a JSON object."
                ]
            )

        if not isinstance(spec, dict):
            return _invalid_result(
                [
                    "spec_json must contain a JSON object."
                ]
            )

        questions, specification_errors = (
            _validate_spec(spec)
        )

        validation = _base_validation()
        validation["errors"].extend(
            specification_errors
        )

        catalog_profile, catalog_warnings = (
            _load_catalog_profile()
        )

        validation["warnings"].extend(
            catalog_warnings
        )

        if questions:
            return {
                "status": "needs_clarification",
                "questions": questions,
                "xml": None,
                "validation": validation,
            }

        if validation["errors"]:
            return {
                "status": "invalid",
                "questions": [],
                "xml": None,
                "validation": validation,
            }

        catalog_errors, catalog_validated = (
            _validate_catalog(
                spec,
                catalog_profile,
            )
        )

        validation["errors"].extend(
            catalog_errors
        )

        validation["catalog_validated"] = (
            catalog_validated
        )

        validation["service_event_map_validated"] = (
            catalog_validated
        )

        if validation["errors"]:
            return {
                "status": "invalid",
                "questions": [],
                "xml": None,
                "validation": validation,
            }

        try:
            _assign_ids(spec)
            xml = _render(spec)

            validation["errors"].extend(
                _validate_xml(xml, spec)
            )

        except (
            KeyError,
            TypeError,
            ValueError,
        ) as exc:
            validation["errors"].append(str(exc))
            xml = None

        if xml is not None and not validation["errors"]:
            (
                xsd_errors,
                xsd_validated,
                xsd_warnings,
            ) = _validate_xsd(xml)

            validation["errors"].extend(
                xsd_errors
            )

            validation["warnings"].extend(
                xsd_warnings
            )

            validation["xsd_validated"] = (
                xsd_validated
            )

        if validation["errors"]:
            return {
                "status": "invalid",
                "questions": [],
                "xml": None,
                "validation": validation,
            }

        validation["reference_validated"] = True
        validation["documentation_rules_validated"] = True

        if not validation["xsd_validated"]:
            validation["warnings"].append(
                "The result is not import-certified because "
                "Oracle installation XSD validation was not completed."
            )

        return {
            "status": "valid",
            "questions": [],
            "xml": xml,
            "validation": validation,
        }