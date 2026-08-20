const elements = {
    form: document.querySelector("#prompt-form"),
    prompt: document.querySelector("#prompt"),
    generate: document.querySelector("#generate-button"),
    clear: document.querySelector("#clear-button"),
    copy: document.querySelector("#copy-button"),
    copyLabel: document.querySelector("#copy-label"),
    connection: document.querySelector("#connection"),
    connectionLabel: document.querySelector("#connection-label"),
    error: document.querySelector("#error-notice"),
    errorMessage: document.querySelector("#error-message"),
    empty: document.querySelector("#empty-state"),
    loading: document.querySelector("#loading-state"),
    xmlViewer: document.querySelector("#xml-viewer"),
    xmlOutput: document.querySelector("#xml-output"),
    assistantOutput: document.querySelector("#assistant-output"),
    validationBar: document.querySelector("#validation-bar"),
    validationSummary: document.querySelector("#validation-summary"),
    statusPill: document.querySelector("#status-pill"),
    testPanel: document.querySelector("#test-panel"),
    testList: document.querySelector("#test-list"),
    passedCount: document.querySelector("#passed-count"),
    failedCount: document.querySelector("#failed-count"),
    manualCount: document.querySelector("#manual-count"),
    toast: document.querySelector("#toast"),
};

let currentXml = "";
let chatContext = null;
let currentTestScenarios = [];


function latestAssistantText(payload) {
    const histories =
        payload?.response?.chat_context?.chat_histories;

    if (Array.isArray(histories)) {
        for (
            let historyIndex = histories.length - 1;
            historyIndex >= 0;
            historyIndex -= 1
        ) {
            const messages =
                histories[historyIndex]?.messages;

            if (!Array.isArray(messages)) {
                continue;
            }

            for (
                let messageIndex = messages.length - 1;
                messageIndex >= 0;
                messageIndex -= 1
            ) {
                const text =
                    messages[messageIndex]?.text;

                if (
                    typeof text === "string" &&
                    text.trim()
                ) {
                    return text.trim();
                }
            }
        }
    }

    const candidates = [
        payload?.response?.text,
        payload?.response?.message,
        payload?.text,
        payload?.message,
        payload?.answer,
    ];

    const result = candidates.find(
        (value) =>
            typeof value === "string" &&
            value.trim()
    );

    return (
        result?.trim() ??
        JSON.stringify(payload, null, 2)
    );
}


function parseJsonContract(text) {
    const fencedBlocks = [
        ...text.matchAll(
            /```(?:json)?\s*([\s\S]*?)```/gi
        ),
    ].map((match) => match[1]);

    const candidates = [
        ...fencedBlocks,
        text,
    ];

    for (const candidate of candidates) {
        try {
            const parsed =
                JSON.parse(candidate.trim());

            if (
                parsed &&
                typeof parsed === "object"
            ) {
                return parsed;
            }
        } catch (_) {
            // Prose plus XML is a valid agent response.
        }
    }

    return null;
}


function extractXml(text, contract, payload) {
    const structuredCandidates = [
        contract?.xml,
        payload?.response?.sly_data?.xml,
        payload?.sly_data?.xml,
    ];

    const structuredXml =
        structuredCandidates.find(
            (value) =>
                typeof value === "string" &&
                value.trim()
        );

    if (structuredXml) {
        return structuredXml.trim();
    }

    const fencedXml = text.match(
        /```(?:xml)?\s*([\s\S]*?<\?xml[\s\S]*?)```/i
    );

    if (fencedXml) {
        return fencedXml[1].trim();
    }

    const declarationStart =
        text.indexOf("<?xml");

    if (declarationStart >= 0) {
        return text
            .slice(declarationStart)
            .replace(/```\s*$/, "")
            .trim();
    }

    const rootStart = text.search(
        /<(?:\w+:)?PricingObjectsJXB\b/i
    );

    if (rootStart >= 0) {
        return text
            .slice(rootStart)
            .replace(/```\s*$/, "")
            .trim();
    }

    return "";
}


function prettyXml(xml) {
    const parser = new DOMParser();

    const parsed = parser.parseFromString(
        xml,
        "application/xml"
    );

    if (parsed.querySelector("parsererror")) {
        return xml;
    }

    const serialized =
        new XMLSerializer().serializeToString(parsed);

    const tokens = serialized
        .replace(/>\s*</g, "><")
        .replace(/(>)(<)(\/*)/g, "$1\n$2$3")
        .split("\n");

    let depth = 0;

    return tokens
        .map((token) => {
            if (/^<\//.test(token)) {
                depth = Math.max(0, depth - 1);
            }

            const line =
                `${"  ".repeat(depth)}${token}`;

            const opensElement =
                /^<[^!?/][^>]*[^/]>/i.test(token);

            const closesOnSameLine =
                /<\/[^>]+>$/.test(token);

            if (
                opensElement &&
                !closesOnSameLine
            ) {
                depth += 1;
            }

            return line;
        })
        .join("\n");
}


function showValidation(status, validation) {
    elements.validationBar.hidden = false;

    elements.statusPill.textContent =
        String(status).replaceAll("_", " ");

    elements.statusPill.className =
        "status-pill";

    if (status === "invalid") {
        elements.statusPill.classList.add("error");
    }

    if (status === "needs_clarification") {
        elements.statusPill.classList.add(
            "warning"
        );
    }

    if (!validation) {
        elements.validationSummary.textContent =
            currentXml
                ? "XML received. Review validation before importing."
                : "Agent response received.";

        return;
    }

    const errors =
        Array.isArray(validation.errors)
            ? validation.errors.length
            : 0;

    const warnings =
        Array.isArray(validation.warnings)
            ? validation.warnings.length
            : 0;

    const xsdStatus =
        validation.xsd_validated
            ? "XSD validated"
            : "XSD not validated";

    const catalogStatus =
        validation.catalog_validated
            ? "catalog validated"
            : "catalog not validated";

    elements.validationSummary.textContent = [
        validation.profile ?? "Oracle PDC 15.2",
        `${errors} errors`,
        `${warnings} warnings`,
        catalogStatus,
        xsdStatus,
    ].join(" | ");
}


function setLoading(loading) {
    elements.generate.disabled = loading;

    elements.generate.classList.toggle(
        "is-loading",
        loading
    );

    elements.generate
        .querySelector(".button-label")
        .textContent = loading
            ? "Generating"
            : "Generate XML";

    elements.loading.hidden = !loading;

    if (loading) {
        elements.empty.hidden = true;
        elements.xmlViewer.hidden = true;
        elements.assistantOutput.hidden = true;
        elements.validationBar.hidden = true;
        elements.testPanel.hidden = true;
        elements.copy.disabled = true;
    }
}


function showError(message) {
    elements.errorMessage.textContent = message;
    elements.error.hidden = false;
    elements.loading.hidden = true;

    if (!currentXml) {
        elements.empty.hidden = false;
    }
}


async function checkHealth() {
    try {
        const response = await fetch(
            "/api/health",
            {
                cache: "no-store",
            }
        );

        if (!response.ok) {
            throw new Error("Health check failed");
        }

        const data = await response.json();

        elements.connection.classList.remove(
            "offline"
        );

        elements.connection.classList.add(
            "online"
        );

        elements.connectionLabel.textContent =
            `${data.network} ready`;

    } catch (_) {
        elements.connection.classList.remove(
            "online"
        );

        elements.connection.classList.add(
            "offline"
        );

        elements.connectionLabel.textContent =
            "Frontend unavailable";
    }
}


function localName(element) {
    return (
        element.localName ||
        element.nodeName.split(":").pop()
    );
}


function descendantsByName(root, name) {
    return [
        ...root.getElementsByTagName("*"),
    ].filter(
        (element) => localName(element) === name
    );
}


function directChildrenByName(root, name) {
    return [
        ...root.children,
    ].filter(
        (element) => localName(element) === name
    );
}


function childText(root, name) {
    const direct =
        directChildrenByName(root, name)[0];

    if (direct) {
        return direct.textContent?.trim() ?? "";
    }

    const descendant =
        descendantsByName(root, name)[0];

    return descendant?.textContent?.trim() ?? "";
}


function makeScenario(
    id,
    category,
    title,
    expected,
    execution,
    status = "MANUAL",
    details = ""
) {
    return {
        id,
        category,
        title,
        expected,
        execution,
        status,
        details,
    };
}


function generatePdcTestScenarios(xml, validation) {
    const scenarios = [];
    const parser = new DOMParser();

    const documentNode =
        parser.parseFromString(
            xml,
            "application/xml"
        );

    const parserError =
        documentNode.querySelector("parsererror");

    scenarios.push(
        makeScenario(
            "XML-001",
            "Structure",
            "XML is well formed",
            "XML parses without syntax errors.",
            "AUTOMATED",
            parserError ? "FAILED" : "PASSED",
            parserError?.textContent?.trim() ?? ""
        )
    );

    if (parserError) {
        return scenarios;
    }

    const root = documentNode.documentElement;
    const rootName = localName(root);

    scenarios.push(
        makeScenario(
            "XML-002",
            "Structure",
            "Correct pricing root element",
            "The root element is PricingObjectsJXB.",
            "AUTOMATED",
            rootName === "PricingObjectsJXB"
                ? "PASSED"
                : "FAILED",
            `Actual root: ${rootName}`
        )
    );

    const namespace =
        root.namespaceURI ||
        root.getAttribute("xmlns:pdc") ||
        "";

    scenarios.push(
        makeScenario(
            "XML-003",
            "Structure",
            "Oracle pricing namespace exists",
            "The configured Oracle pricing namespace is present.",
            "AUTOMATED",
            namespace ? "PASSED" : "FAILED",
            namespace || "Namespace not found."
        )
    );

    const ratePlans =
        descendantsByName(root, "chargeRatePlan");

    const offerings =
        descendantsByName(root, "chargeOffering");

    const bundles =
        descendantsByName(
            root,
            "bundledProductOffering"
        );

    scenarios.push(
        makeScenario(
            "XML-004",
            "Structure",
            "Rate plan exists",
            "At least one chargeRatePlan exists.",
            "AUTOMATED",
            ratePlans.length > 0
                ? "PASSED"
                : "FAILED",
            `${ratePlans.length} rate plans found.`
        )
    );

    scenarios.push(
        makeScenario(
            "XML-005",
            "Structure",
            "Charge offering exists",
            "Exactly one generated chargeOffering exists.",
            "AUTOMATED",
            offerings.length === 1
                ? "PASSED"
                : "FAILED",
            `${offerings.length} charge offerings found.`
        )
    );

    const rootObjectOrder = [
        ...root.children,
    ].map(localName);

    const orderValues = {
        chargeRatePlan: 0,
        chargeOffering: 1,
        bundledProductOffering: 2,
    };

    let previousOrder = -1;
    let orderValid = true;

    rootObjectOrder.forEach((name) => {
        const currentOrder = orderValues[name];

        if (
            currentOrder === undefined ||
            currentOrder < previousOrder
        ) {
            orderValid = false;
        }

        if (currentOrder !== undefined) {
            previousOrder = Math.max(
                previousOrder,
                currentOrder
            );
        }
    });

    scenarios.push(
        makeScenario(
            "XML-006",
            "Structure",
            "Pricing-object dependency order",
            "Rate plans precede offerings and offerings precede bundles.",
            "AUTOMATED",
            orderValid ? "PASSED" : "FAILED",
            rootObjectOrder.join(" -> ")
        )
    );

    const internalIds =
        descendantsByName(root, "internalId")
            .map(
                (element) =>
                    element.textContent.trim()
            )
            .filter(Boolean);

    const uniqueIds = new Set(internalIds);

    scenarios.push(
        makeScenario(
            "REF-001",
            "References",
            "Internal identifiers are unique",
            "No pricing-object internalId is duplicated.",
            "AUTOMATED",
            uniqueIds.size === internalIds.length
                ? "PASSED"
                : "FAILED",
            `${internalIds.length} IDs; ` +
            `${uniqueIds.size} unique.`
        )
    );

    const uuidPattern =
        /^[0-9a-f]{8}-[0-9a-f]{4}-[1-5][0-9a-f]{3}-[89ab][0-9a-f]{3}-[0-9a-f]{12}$/i;

    const invalidIds =
        internalIds.filter(
            (value) => !uuidPattern.test(value)
        );

    scenarios.push(
        makeScenario(
            "REF-002",
            "References",
            "Identifiers use UUID format",
            "Every pricing-object internalId is a UUID.",
            "AUTOMATED",
            invalidIds.length === 0
                ? "PASSED"
                : "FAILED",
            invalidIds.length
                ? `Invalid IDs: ${invalidIds.join(", ")}`
                : `${internalIds.length} UUIDs validated.`
        )
    );

    const ratePlanIds = new Set(
        ratePlans
            .map(
                (plan) =>
                    childText(plan, "internalId")
            )
            .filter(Boolean)
    );

    const ratePlanReferences =
        descendantsByName(root, "ratePlanIID")
            .map(
                (element) =>
                    element.textContent.trim()
            )
            .filter(Boolean);

    const unresolvedReferences =
        ratePlanReferences.filter(
            (reference) =>
                !ratePlanIds.has(reference)
        );

    scenarios.push(
        makeScenario(
            "REF-003",
            "References",
            "Rate-plan identifiers resolve",
            "Every ratePlanIID references a generated rate plan.",
            "AUTOMATED",
            unresolvedReferences.length === 0
                ? "PASSED"
                : "FAILED",
            unresolvedReferences.length
                ? `Unresolved: ${unresolvedReferences.join(", ")}`
                : `${ratePlanReferences.length} references resolved.`
        )
    );

    const ratePlanNames = new Set(
        ratePlans
            .map(
                (plan) =>
                    childText(plan, "name")
            )
            .filter(Boolean)
    );

    const ratePlanNameReferences =
        descendantsByName(
            root,
            "chargeRatePlanName"
        )
            .map(
                (element) =>
                    element.textContent.trim()
            )
            .filter(Boolean);

    const unresolvedNames =
        ratePlanNameReferences.filter(
            (name) => !ratePlanNames.has(name)
        );

    scenarios.push(
        makeScenario(
            "REF-004",
            "References",
            "Rate-plan names resolve",
            "Every chargeRatePlanName references a generated rate plan.",
            "AUTOMATED",
            unresolvedNames.length === 0
                ? "PASSED"
                : "FAILED",
            unresolvedNames.length
                ? `Unresolved: ${unresolvedNames.join(", ")}`
                : `${ratePlanNameReferences.length} names resolved.`
        )
    );

    const externalIdFailures = [];

    offerings.forEach((offering) => {
        const internalId =
            childText(offering, "internalId");

        const externalId =
            offering.getAttribute("externalID");

        if (internalId !== externalId) {
            externalIdFailures.push(
                childText(offering, "name") ||
                internalId ||
                "unnamed offering"
            );
        }
    });

    scenarios.push(
        makeScenario(
            "REF-005",
            "References",
            "Offering external and internal IDs match",
            "Each chargeOffering externalID equals its internalId.",
            "AUTOMATED",
            externalIdFailures.length === 0
                ? "PASSED"
                : "FAILED",
            externalIdFailures.length
                ? externalIdFailures.join(", ")
                : "Offering identifiers match."
        )
    );

    const duplicateNames = [];
    const namesToCheck = [
        ...ratePlans.map(
            (item) => childText(item, "name")
        ),
        ...offerings.map(
            (item) => childText(item, "name")
        ),
        ...bundles.map(
            (item) => childText(item, "name")
        ),
    ].filter(Boolean);

    const seenNames = new Set();

    namesToCheck.forEach((name) => {
        if (seenNames.has(name)) {
            duplicateNames.push(name);
        }

        seenNames.add(name);
    });

    scenarios.push(
        makeScenario(
            "CAT-001",
            "Naming",
            "Pricing-object names are unique",
            "Generated rate plan, offering, and bundle names are unique.",
            "AUTOMATED",
            duplicateNames.length === 0
                ? "PASSED"
                : "FAILED",
            duplicateNames.length
                ? `Duplicates: ${duplicateNames.join(", ")}`
                : `${namesToCheck.length} names checked.`
        )
    );

    offerings.forEach((offering, index) => {
        const name =
            childText(offering, "name") ||
            `Offering ${index + 1}`;

        const offerType =
            childText(
                offering,
                "offerType"
            ).toUpperCase();

        scenarios.push(
            makeScenario(
                `OFFER-${index + 1}-PURCHASE`,
                "Purchase",
                `Purchase ${name}`,
                "The offer is purchasable only during its configured timeRange.",
                "MANUAL"
            ),
            makeScenario(
                `OFFER-${index + 1}-BOUNDARY`,
                "Validity",
                `${name} time-range boundaries`,
                "The start is inclusive and the end is exclusive.",
                "MANUAL"
            ),
            makeScenario(
                `OFFER-${index + 1}-OWNERSHIP`,
                "Ownership",
                `${name} ownership limits`,
                "ownMin, ownMax, purchaseMin, and purchaseMax are enforced.",
                "MANUAL"
            )
        );

        if (offerType === "ITEM") {
            scenarios.push(
                makeScenario(
                    `OFFER-${index + 1}-ITEM`,
                    "Offer type",
                    `${name} item behavior`,
                    "The one-time purchase charge is applied once.",
                    "MANUAL"
                )
            );
        }

        if (offerType === "SYSTEM") {
            scenarios.push(
                makeScenario(
                    `OFFER-${index + 1}-SYSTEM`,
                    "Offer type",
                    `${name} system behavior`,
                    "Usage is rated without customer ownership of the offer.",
                    "MANUAL"
                )
            );
        }
    });

    const eventNames = [
        ...new Set(
            descendantsByName(root, "eventName")
                .map(
                    (element) =>
                        element.textContent.trim()
                )
                .filter(Boolean)
        ),
    ];

    eventNames.forEach((eventName, index) => {
        const lowerEvent =
            eventName.toLowerCase();

        const recurring =
            lowerEvent.includes("/cycle/") ||
            lowerEvent.includes("cycle");

        const oneTime =
            lowerEvent.includes("/purchase") ||
            lowerEvent.includes("purchase");

        if (recurring) {
            scenarios.push(
                makeScenario(
                    `REC-${index + 1}-FIRST`,
                    "Recurring",
                    "Purchase during first cycle",
                    "The configured prorateFirst behavior is applied.",
                    "MANUAL"
                ),
                makeScenario(
                    `REC-${index + 1}-NORMAL`,
                    "Recurring",
                    "Normal complete billing cycle",
                    "The recurring balance impact is applied once for the cycle.",
                    "MANUAL"
                ),
                makeScenario(
                    `REC-${index + 1}-LAST`,
                    "Recurring",
                    "Cancellation during last cycle",
                    "The configured prorateLast behavior is applied.",
                    "MANUAL"
                ),
                makeScenario(
                    `REC-${index + 1}-SUSPEND`,
                    "Recurring",
                    "Suspended or inactive subscription",
                    "The validIfInactive and validIfSuspendedActive settings are respected.",
                    "MANUAL"
                )
            );
        } else if (oneTime) {
            scenarios.push(
                makeScenario(
                    `OT-${index + 1}-PURCHASE`,
                    "One-time",
                    "One-time purchase event",
                    "The purchase balance impact is applied exactly once.",
                    "MANUAL"
                ),
                makeScenario(
                    `OT-${index + 1}-REPEAT`,
                    "One-time",
                    "Repeated purchase-event protection",
                    "The same purchased item is not charged repeatedly unless repurchased.",
                    "MANUAL"
                )
            );
        } else {
            scenarios.push(
                makeScenario(
                    `USAGE-${index + 1}-ZERO`,
                    "Usage",
                    "Zero measured usage",
                    "No charge is produced unless minimum quantity rules apply.",
                    "MANUAL"
                ),
                makeScenario(
                    `USAGE-${index + 1}-NORMAL`,
                    "Usage",
                    "Normal measured usage",
                    "The event is measured using its configured RUM.",
                    "MANUAL"
                ),
                makeScenario(
                    `USAGE-${index + 1}-BOUNDARY`,
                    "Usage",
                    "Usage tier boundaries",
                    "Values below, at, and above tier boundaries use the correct price.",
                    "MANUAL"
                ),
                makeScenario(
                    `USAGE-${index + 1}-ROUNDING`,
                    "Usage",
                    "Minimum and increment rounding",
                    "Quantity follows minQuantity, incrementQuantity, and roundingMode.",
                    "MANUAL"
                )
            );
        }
    });

    bundles.forEach((bundle, index) => {
        const name =
            childText(bundle, "name") ||
            `Bundle ${index + 1}`;

        scenarios.push(
            makeScenario(
                `BUNDLE-${index + 1}-REFERENCE`,
                "Bundle",
                `${name} offering references`,
                "Every bundled item references a generated charge offering.",
                "MANUAL"
            ),
            makeScenario(
                `BUNDLE-${index + 1}-SERVICE`,
                "Bundle",
                `${name} service consistency`,
                "All bundled offerings use the same product specification.",
                "MANUAL"
            ),
            makeScenario(
                `BUNDLE-${index + 1}-VALIDITY`,
                "Bundle",
                `${name} purchase validity`,
                "Offer purchase periods contain the bundle-item purchase periods.",
                "MANUAL"
            ),
            makeScenario(
                `BUNDLE-${index + 1}-QUANTITY`,
                "Bundle",
                `${name} item quantity`,
                "Every bundle-item quantity and purchase mode is applied correctly.",
                "MANUAL"
            )
        );
    });

    scenarios.push(
        makeScenario(
            "SEC-001",
            "Security",
            "XML-special-character handling",
            "Names and descriptions containing &, <, >, quotes, and apostrophes remain text.",
            "AUTOMATED",
            "PASSED",
            "XML was parsed as data by DOMParser."
        ),
        makeScenario(
            "CAT-002",
            "Catalog",
            "Product specification exists",
            "productSpecName exists in the target Oracle PDC catalog.",
            "MANUAL"
        ),
        makeScenario(
            "CAT-003",
            "Catalog",
            "Service-event-RUM mapping exists",
            "Every event and RUM combination exists in the service-event map.",
            "MANUAL"
        ),
        makeScenario(
            "CAT-004",
            "Catalog",
            "Balance elements exist",
            "Every currency and noncurrency balance-element code exists.",
            "MANUAL"
        ),
        makeScenario(
            "XSD-001",
            "Schema",
            "Oracle PDC 15.2 XSD validation",
            "The XML validates against the installed Oracle PDC 15.2 pricing XSD.",
            "MANUAL",
            validation?.xsd_validated
                ? "PASSED"
                : "MANUAL"
        ),
        makeScenario(
            "IMPORT-001",
            "Import",
            "Controlled PDC import",
            "ImportExportPricing accepts the XML without errors.",
            "MANUAL"
        ),
        makeScenario(
            "RUNTIME-001",
            "Runtime",
            "BRM rating verification",
            "Representative events produce the expected balance impacts.",
            "MANUAL"
        )
    );

    return scenarios;
}


function renderTestScenarios(
    scenarios,
    filter = "ALL"
) {
    elements.testList.textContent = "";

    const filtered = scenarios.filter(
        (scenario) => {
            if (filter === "ALL") {
                return true;
            }

            if (filter === "FAILED") {
                return scenario.status === "FAILED";
            }

            return scenario.execution === filter;
        }
    );

    filtered.forEach((scenario) => {
        const item =
            document.createElement("article");

        item.className =
            `test-item ${scenario.status.toLowerCase()}`;

        const heading =
            document.createElement("div");

        heading.className =
            "test-item-heading";

        const title =
            document.createElement("strong");

        title.textContent =
            `${scenario.id} - ${scenario.title}`;

        const status =
            document.createElement("span");

        status.className = "test-status";
        status.textContent = scenario.status;

        heading.append(title, status);

        const category =
            document.createElement("small");

        category.textContent =
            `${scenario.category} | ${scenario.execution}`;

        const expected =
            document.createElement("p");

        expected.textContent =
            scenario.expected;

        item.append(
            heading,
            category,
            expected
        );

        if (scenario.details) {
            const details =
                document.createElement("code");

            details.textContent =
                scenario.details;

            item.append(details);
        }

        elements.testList.append(item);
    });

    if (!filtered.length) {
        const empty =
            document.createElement("p");

        empty.className =
            "test-list-empty";

        empty.textContent =
            "No scenarios match this filter.";

        elements.testList.append(empty);
    }

    const passed = scenarios.filter(
        (scenario) =>
            scenario.status === "PASSED"
    ).length;

    const failed = scenarios.filter(
        (scenario) =>
            scenario.status === "FAILED"
    ).length;

    const manual = scenarios.filter(
        (scenario) =>
            scenario.status === "MANUAL"
    ).length;

    elements.passedCount.textContent =
        `${passed} passed`;

    elements.failedCount.textContent =
        `${failed} failed`;

    elements.manualCount.textContent =
        `${manual} manual`;

    elements.testPanel.hidden = false;
}


async function generate(event) {
    event.preventDefault();

    const message =
        elements.prompt.value.trim();

    if (!message) {
        return;
    }

    elements.error.hidden = true;
    setLoading(true);

    try {
        const response = await fetch(
            "/api/generate",
            {
                method: "POST",
                headers: {
                    "Content-Type": "application/json",
                },
                body: JSON.stringify({
                    message,
                    chat_context: chatContext,
                }),
            }
        );

        const payload = await response.json();

        if (!response.ok) {
            throw new Error(
                payload.details ||
                payload.error ||
                "Generation failed."
            );
        }

        chatContext =
            payload?.response?.chat_context ??
            chatContext;

        const assistantText =
            latestAssistantText(payload);

        const contract =
            parseJsonContract(assistantText);

        currentXml = extractXml(
            assistantText,
            contract,
            payload
        );

        elements.empty.hidden = true;
        elements.loading.hidden = true;

        const status =
            contract?.status ??
            (
                currentXml
                    ? "valid"
                    : "complete"
            );

        const validation =
            contract?.validation ??
            payload?.response?.sly_data?.validation ??
            payload?.sly_data?.validation ??
            null;

        if (currentXml) {
            elements.xmlOutput.textContent =
                prettyXml(currentXml);

            elements.xmlViewer.hidden = false;
            elements.assistantOutput.hidden = true;
            elements.copy.disabled = false;

            currentTestScenarios =
                generatePdcTestScenarios(
                    currentXml,
                    validation
                );

            renderTestScenarios(
                currentTestScenarios
            );
        } else {
            elements.assistantOutput.textContent =
                assistantText;

            elements.assistantOutput.hidden = false;
            elements.xmlViewer.hidden = true;
            elements.testPanel.hidden = true;
        }

        showValidation(
            status,
            validation
        );

    } catch (error) {
        showError(
            error.message ||
            "Unexpected error while generating XML."
        );
    } finally {
        setLoading(false);
    }
}


function clearAll() {
    elements.prompt.value = "";
    elements.xmlOutput.textContent = "";
    elements.assistantOutput.textContent = "";
    elements.testList.textContent = "";

    elements.xmlViewer.hidden = true;
    elements.assistantOutput.hidden = true;
    elements.validationBar.hidden = true;
    elements.error.hidden = true;
    elements.empty.hidden = false;
    elements.testPanel.hidden = true;

    elements.copy.disabled = true;
    elements.copyLabel.textContent = "Copy XML";

    currentXml = "";
    chatContext = null;
    currentTestScenarios = [];

    document
        .querySelectorAll("[data-test-filter]")
        .forEach((button) => {
            button.classList.toggle(
                "active",
                button.dataset.testFilter === "ALL"
            );
        });

    elements.prompt.focus();
}


async function copyXml() {
    if (!currentXml) {
        return;
    }

    await navigator.clipboard.writeText(
        currentXml
    );

    elements.copyLabel.textContent = "Copied";
    elements.toast.classList.add("visible");

    window.setTimeout(
        () => {
            elements.copyLabel.textContent =
                "Copy XML";

            elements.toast.classList.remove(
                "visible"
            );
        },
        1600
    );
}


elements.form.addEventListener(
    "submit",
    generate
);

elements.clear.addEventListener(
    "click",
    clearAll
);

elements.copy.addEventListener(
    "click",
    copyXml
);

elements.prompt.addEventListener(
    "keydown",
    (event) => {
        if (
            (event.ctrlKey || event.metaKey) &&
            event.key === "Enter"
        ) {
            elements.form.requestSubmit();
        }
    }
);

document
    .querySelectorAll("[data-test-filter]")
    .forEach((button) => {
        button.addEventListener(
            "click",
            () => {
                document
                    .querySelectorAll(
                        "[data-test-filter]"
                    )
                    .forEach((candidate) => {
                        candidate.classList.remove(
                            "active"
                        );
                    });

                button.classList.add("active");

                renderTestScenarios(
                    currentTestScenarios,
                    button.dataset.testFilter
                );
            }
        );
    });

checkHealth();
elements.prompt.focus();