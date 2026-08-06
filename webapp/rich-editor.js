(() => {
    const BLOCK_TAGS = new Set([
        "DIV",
        "P",
        "BLOCKQUOTE",
        "PRE",
        "LI",
    ]);

    const ENTITY_PRIORITY = {
        pre: 0,
        blockquote: 1,
        expandable_blockquote: 1,
        bold: 2,
        italic: 3,
        underline: 4,
        strikethrough: 5,
        spoiler: 6,
        code: 7,
        text_link: 8,
    };

    function appendTextWithBreaks(parent, value) {
        const parts = value.split("\n");

        parts.forEach((part, index) => {
            if (part) {
                parent.append(document.createTextNode(part));
            }

            if (index < parts.length - 1) {
                parent.append(document.createElement("br"));
            }
        });
    }

    function createEntityElement(entity) {
        const elementByType = {
            bold: "strong",
            italic: "em",
            underline: "u",
            strikethrough: "s",
            spoiler: "span",
            blockquote: "blockquote",
            expandable_blockquote: "blockquote",
            code: "code",
            pre: "pre",
            text_link: "a",
        };
        const element = document.createElement(
            elementByType[entity.type] || "span",
        );

        element.dataset.entityType = entity.type;

        if (entity.type === "spoiler") {
            element.className = "tg-spoiler";
        }

        if (entity.type === "expandable_blockquote") {
            element.dataset.expandable = "true";
        }

        if (entity.type === "text_link") {
            element.href = entity.url;
            element.target = "_blank";
            element.rel = "noopener noreferrer";
        }

        if (entity.type === "pre" && entity.language) {
            element.dataset.language = entity.language;
        }

        return element;
    }

    function buildEntityTree(entities, textLength) {
        const sorted = [...entities]
            .filter((entity) => (
                Number.isInteger(entity.offset)
                && Number.isInteger(entity.length)
                && entity.offset >= 0
                && entity.length > 0
                && entity.offset + entity.length <= textLength
            ))
            .sort((left, right) => (
                left.offset - right.offset
                || right.length - left.length
                || (
                    ENTITY_PRIORITY[left.type] ?? 99
                ) - (
                    ENTITY_PRIORITY[right.type] ?? 99
                )
            ));

        const roots = [];
        const stack = [];

        for (const entity of sorted) {
            const node = {
                entity,
                children: [],
            };
            const start = entity.offset;
            const end = start + entity.length;

            while (stack.length) {
                const parent = stack[stack.length - 1];
                const parentEnd = (
                    parent.entity.offset
                    + parent.entity.length
                );

                if (start >= parentEnd) {
                    stack.pop();
                    continue;
                }

                break;
            }

            if (stack.length) {
                const parent = stack[stack.length - 1];
                const parentEnd = (
                    parent.entity.offset
                    + parent.entity.length
                );

                if (end <= parentEnd) {
                    parent.children.push(node);
                } else {
                    continue;
                }
            } else {
                roots.push(node);
            }

            stack.push(node);
        }

        return roots;
    }

    function renderRange(parent, text, start, end, nodes) {
        let cursor = start;

        for (const node of nodes) {
            const entityStart = node.entity.offset;
            const entityEnd = entityStart + node.entity.length;

            if (entityStart > cursor) {
                appendTextWithBreaks(
                    parent,
                    text.slice(cursor, entityStart),
                );
            }

            const wrapper = createEntityElement(node.entity);
            renderRange(
                wrapper,
                text,
                entityStart,
                entityEnd,
                node.children,
            );
            parent.append(wrapper);
            cursor = entityEnd;
        }

        if (cursor < end) {
            appendTextWithBreaks(
                parent,
                text.slice(cursor, end),
            );
        }
    }

    function renderDocument(root, text, entities) {
        root.replaceChildren();

        if (!text) {
            return;
        }

        const tree = buildEntityTree(entities, text.length);
        renderRange(root, text, 0, text.length, tree);
    }

    function entityTypesForElement(element) {
        const types = [];
        const tagName = element.tagName;
        const explicit = element.dataset.entityType;

        if (explicit) {
            types.push(explicit);
        } else {
            if (tagName === "STRONG" || tagName === "B") {
                types.push("bold");
            }
            if (tagName === "EM" || tagName === "I") {
                types.push("italic");
            }
            if (tagName === "U") {
                types.push("underline");
            }
            if (
                tagName === "S"
                || tagName === "STRIKE"
                || tagName === "DEL"
            ) {
                types.push("strikethrough");
            }
            if (tagName === "CODE") {
                types.push("code");
            }
            if (tagName === "PRE") {
                types.push("pre");
            }
            if (tagName === "BLOCKQUOTE") {
                types.push(
                    element.dataset.expandable === "true"
                        ? "expandable_blockquote"
                        : "blockquote",
                );
            }
            if (tagName === "A") {
                types.push("text_link");
            }
        }

        const style = element.style;
        const decoration = style.textDecorationLine
            || style.textDecoration
            || "";

        if (
            style.fontWeight === "bold"
            || Number(style.fontWeight) >= 600
        ) {
            types.push("bold");
        }
        if (style.fontStyle === "italic") {
            types.push("italic");
        }
        if (decoration.includes("underline")) {
            types.push("underline");
        }
        if (decoration.includes("line-through")) {
            types.push("strikethrough");
        }

        return [...new Set(types)];
    }

    function serializeDocument(root) {
        let text = "";
        const entities = [];

        function append(value) {
            text += value;
        }

        function ensureLineBreakBefore() {
            if (text && !text.endsWith("\n")) {
                append("\n");
            }
        }

        function walk(node) {
            if (node.nodeType === Node.TEXT_NODE) {
                append(node.nodeValue || "");
                return;
            }

            if (node.nodeType !== Node.ELEMENT_NODE) {
                return;
            }

            const element = node;

            if (element.tagName === "BR") {
                append("\n");
                return;
            }

            const isBlock = BLOCK_TAGS.has(element.tagName);

            if (isBlock) {
                ensureLineBreakBefore();
            }

            const start = text.length;

            for (const child of element.childNodes) {
                walk(child);
            }

            const end = text.length;

            for (const type of entityTypesForElement(element)) {
                if (end <= start) {
                    continue;
                }

                const entity = {
                    type,
                    offset: start,
                    length: end - start,
                };

                if (type === "text_link") {
                    entity.url = element.getAttribute("href") || "";
                }

                if (type === "pre" && element.dataset.language) {
                    entity.language = element.dataset.language;
                }

                entities.push(entity);
            }

            if (isBlock && element.nextSibling) {
                ensureLineBreakBefore();
            }
        }

        for (const child of root.childNodes) {
            walk(child);
        }

        while (text.endsWith("\n")) {
            text = text.slice(0, -1);
        }

        const normalizedEntities = entities
            .map((entity) => {
                const maximumLength = text.length - entity.offset;
                return {
                    ...entity,
                    length: Math.min(entity.length, maximumLength),
                };
            })
            .filter((entity) => entity.length > 0)
            .sort((left, right) => (
                left.offset - right.offset
                || right.length - left.length
                || (
                    ENTITY_PRIORITY[left.type] ?? 99
                ) - (
                    ENTITY_PRIORITY[right.type] ?? 99
                )
            ));

        return {
            text,
            entities: normalizedEntities,
        };
    }

    function selectionInside(root) {
        const selection = window.getSelection();

        if (!selection || !selection.rangeCount) {
            return null;
        }

        const range = selection.getRangeAt(0);
        const commonAncestor = range.commonAncestorContainer;

        if (!root.contains(commonAncestor)) {
            return null;
        }

        return { selection, range };
    }

    function wrapSelection(root, tagName, attributes = {}) {
        const current = selectionInside(root);

        if (!current || current.range.collapsed) {
            return false;
        }

        const wrapper = document.createElement(tagName);

        for (const [name, value] of Object.entries(attributes)) {
            if (name === "className") {
                wrapper.className = value;
            } else if (name.startsWith("data-")) {
                wrapper.setAttribute(name, value);
            } else {
                wrapper.setAttribute(name, value);
            }
        }

        const fragment = current.range.extractContents();
        wrapper.append(fragment);
        current.range.insertNode(wrapper);
        current.selection.removeAllRanges();

        const nextRange = document.createRange();
        nextRange.selectNodeContents(wrapper);
        current.selection.addRange(nextRange);
        return true;
    }

    function findClosestElement(root, tagName) {
        const current = selectionInside(root);

        if (!current) {
            return null;
        }

        let node = current.range.startContainer;

        if (node.nodeType === Node.TEXT_NODE) {
            node = node.parentElement;
        }

        while (node && node !== root) {
            if (node.tagName === tagName) {
                return node;
            }
            node = node.parentElement;
        }

        return null;
    }

    class RichTelegramEditor {
        constructor({
            root,
            preview,
            counter,
            toolbar,
            onChange,
        }) {
            this.root = root;
            this.preview = preview;
            this.counter = counter;
            this.toolbar = toolbar;
            this.onChange = onChange || (() => {});
            this.limit = 4096;
            this.lastDocument = { text: "", entities: [] };

            this.root.addEventListener("input", () => {
                this.refresh();
                this.onChange(this.lastDocument);
            });

            this.root.addEventListener("paste", (event) => {
                event.preventDefault();
                const plainText = event.clipboardData?.getData("text/plain") || "";
                document.execCommand("insertText", false, plainText);
            });

            this.root.addEventListener("click", (event) => {
                if (event.target.closest("a")) {
                    event.preventDefault();
                }
            });

            this.toolbar.addEventListener("pointerdown", (event) => {
                if (event.target.closest("button")) {
                    event.preventDefault();
                }
            });

            this.toolbar.addEventListener("click", (event) => {
                const button = event.target.closest("button[data-command]");

                if (!button) {
                    return;
                }

                this.applyCommand(button.dataset.command);
            });
        }

        setLimit(limit) {
            this.limit = limit;
            this.refresh();
        }

        setDocument(text, entities = []) {
            renderDocument(this.root, text || "", entities || []);
            this.refresh();
        }

        getDocument() {
            this.lastDocument = serializeDocument(this.root);
            return this.lastDocument;
        }

        focus() {
            this.root.focus();
        }

        refresh() {
            this.lastDocument = serializeDocument(this.root);
            renderDocument(
                this.preview,
                this.lastDocument.text,
                this.lastDocument.entities,
            );

            const characters = Array.from(this.lastDocument.text).length;
            this.counter.textContent = `${characters} / ${this.limit}`;
            this.counter.dataset.kind = (
                characters > this.limit ? "error" : ""
            );
        }

        applyCommand(command) {
            this.root.focus();

            const nativeCommands = {
                bold: "bold",
                italic: "italic",
                underline: "underline",
                strikethrough: "strikeThrough",
                undo: "undo",
                redo: "redo",
            };

            if (nativeCommands[command]) {
                document.execCommand(nativeCommands[command], false);
            } else if (command === "spoiler") {
                wrapSelection(this.root, "span", {
                    "data-entity-type": "spoiler",
                    className: "tg-spoiler",
                });
            } else if (command === "code") {
                wrapSelection(this.root, "code", {
                    "data-entity-type": "code",
                });
            } else if (command === "quote") {
                document.execCommand("formatBlock", false, "blockquote");
                const quote = findClosestElement(this.root, "BLOCKQUOTE");
                if (quote) {
                    quote.dataset.entityType = "blockquote";
                    delete quote.dataset.expandable;
                }
            } else if (command === "expandable-quote") {
                document.execCommand("formatBlock", false, "blockquote");
                const quote = findClosestElement(this.root, "BLOCKQUOTE");
                if (quote) {
                    quote.dataset.entityType = "expandable_blockquote";
                    quote.dataset.expandable = "true";
                }
            } else if (command === "pre") {
                document.execCommand("formatBlock", false, "pre");
                const block = findClosestElement(this.root, "PRE");
                if (block) {
                    block.dataset.entityType = "pre";
                    const language = window.prompt(
                        "Язык подсветки кода (необязательно)",
                        block.dataset.language || "",
                    );
                    if (language !== null) {
                        block.dataset.language = language.trim().slice(0, 64);
                    }
                }
            } else if (command === "link") {
                const url = window.prompt(
                    "Ссылка для выделенного текста",
                    "https://",
                );
                if (url && /^(https?:|tg:|mailto:)/i.test(url.trim())) {
                    document.execCommand("createLink", false, url.trim());
                    const link = findClosestElement(this.root, "A");
                    if (link) {
                        link.dataset.entityType = "text_link";
                        link.target = "_blank";
                        link.rel = "noopener noreferrer";
                    }
                }
            } else if (command === "clear") {
                document.execCommand("removeFormat", false);
                document.execCommand("unlink", false);
            }

            this.refresh();
            this.onChange(this.lastDocument);
        }
    }

    window.RichTelegramEditor = RichTelegramEditor;
})();
