(() => {
    const telegram = window.Telegram?.WebApp;

    const monthTitle = document.getElementById(
        "month-title",
    );
    const calendarGrid = document.getElementById(
        "calendar-grid",
    );
    const selectedDayTitle = document.getElementById(
        "selected-day-title",
    );
    const publicationCount = document.getElementById(
        "publication-count",
    );
    const publicationList = document.getElementById(
        "publication-list",
    );
    const statusMessage = document.getElementById(
        "status-message",
    );
    const timezoneName = document.getElementById(
        "timezone-name",
    );
    const previousMonthButton =
        document.getElementById(
            "previous-month",
        );
    const nextMonthButton =
        document.getElementById(
            "next-month",
        );
    const refreshButton = document.getElementById(
        "refresh-button",
    );

    const editorOverlay = document.getElementById(
        "editor-overlay",
    );
    const editorClose = document.getElementById(
        "editor-close",
    );
    const editorForm = document.getElementById(
        "editor-form",
    );
    const editorTitle = document.getElementById(
        "editor-title",
    );
    const editorStatus = document.getElementById(
        "editor-status",
    );
    const editorMedia = document.getElementById(
        "editor-media",
    );
    const editorType = document.getElementById(
        "editor-type",
    );
    const editorChannel = document.getElementById(
        "editor-channel",
    );
    const editorScheduledAt =
        document.getElementById(
            "editor-scheduled-at",
        );
    const editorRichText = document.getElementById(
        "editor-rich-text",
    );
    const editorToolbar = document.getElementById(
        "editor-toolbar",
    );
    const editorPreview = document.getElementById(
        "editor-preview",
    );
    const editorCharacterCount = document.getElementById(
        "editor-character-count",
    );
    const editorVersion = document.getElementById(
        "editor-version",
    );
    const editorDirty = document.getElementById(
        "editor-dirty",
    );
    const editorHistoryToggle = document.getElementById(
        "editor-history-toggle",
    );
    const editorHistory = document.getElementById(
        "editor-history",
    );
    const editorHistoryList = document.getElementById(
        "editor-history-list",
    );
    const editorSave = document.getElementById(
        "editor-save",
    );

    const monthNames = [
        "Январь",
        "Февраль",
        "Март",
        "Апрель",
        "Май",
        "Июнь",
        "Июль",
        "Август",
        "Сентябрь",
        "Октябрь",
        "Ноябрь",
        "Декабрь",
    ];

    const contentTypeIcons = {
        text: "T",
        photo: "▧",
        video: "▶",
    };

    const deviceTimezone = (
        Intl.DateTimeFormat()
            .resolvedOptions()
            .timeZone || ""
    ).trim();

    const state = {
        currentMonth: new Date(
            new Date().getFullYear(),
            new Date().getMonth(),
            1,
        ),
        selectedDay: null,
        items: [],
        timezone: deviceTimezone,
        loading: false,
        editorPublicationId: null,
        editorLoading: false,
        editorVersion: 1,
        editorDirty: false,
        editorContentType: "text",
        historyLoading: false,
        mediaObjectUrl: null,
    };

    const richEditor = new window.RichTelegramEditor({
        root: editorRichText,
        preview: editorPreview,
        counter: editorCharacterCount,
        toolbar: editorToolbar,
        onChange: () => setEditorDirty(true),
    });

    function pad(value) {
        return String(value).padStart(2, "0");
    }

    function formatLocalDateTime(date) {
        return [
            date.getFullYear(),
            "-",
            pad(date.getMonth() + 1),
            "-",
            pad(date.getDate()),
            "T",
            pad(date.getHours()),
            ":",
            pad(date.getMinutes()),
        ].join("");
    }

    function getNextAvailableMinute() {
        const nextMinute = new Date();
        nextMinute.setSeconds(0, 0);
        nextMinute.setMinutes(
            nextMinute.getMinutes() + 1,
        );
        return nextMinute;
    }

    function getTimezoneOffsetMinutes(date) {
        return -date.getTimezoneOffset();
    }

    function formatTimezoneLabel(date = new Date()) {
        const offsetMinutes =
            getTimezoneOffsetMinutes(date);
        const sign = offsetMinutes >= 0 ? "+" : "-";
        const absoluteMinutes = Math.abs(offsetMinutes);
        const hours = Math.floor(absoluteMinutes / 60);
        const minutes = absoluteMinutes % 60;
        const offset = (
            `UTC${sign}${pad(hours)}:${pad(minutes)}`
        );

        return state.timezone
            ? `${state.timezone} (${offset})`
            : offset;
    }

    function refreshEditorMinimum(
        { forceValue = false } = {},
    ) {
        const minimum = formatLocalDateTime(
            getNextAvailableMinute(),
        );

        editorScheduledAt.min = minimum;

        if (
            forceValue
            || !editorScheduledAt.value
            || editorScheduledAt.value < minimum
        ) {
            editorScheduledAt.value = minimum;
        }

        return minimum;
    }

    function getMonthKey(date) {
        return [
            date.getFullYear(),
            pad(date.getMonth() + 1),
        ].join("-");
    }

    function getDayKey(date) {
        return [
            date.getFullYear(),
            pad(date.getMonth() + 1),
            pad(date.getDate()),
        ].join("-");
    }

    function formatSelectedDay(dayKey) {
        const [year, month, day] = dayKey
            .split("-")
            .map(Number);

        return new Intl.DateTimeFormat(
            "ru-RU",
            {
                day: "numeric",
                month: "long",
                year: "numeric",
            },
        ).format(
            new Date(year, month - 1, day),
        );
    }

    function setStatus(message, kind = "") {
        statusMessage.textContent = message;
        statusMessage.dataset.kind = kind;
    }

    function setEditorStatus(
        message,
        kind = "",
    ) {
        editorStatus.textContent = message;
        editorStatus.dataset.kind = kind;
    }

    function getAuthHeaders(
        contentType = false,
    ) {
        const headers = {
            "X-Telegram-Init-Data":
                telegram?.initData || "",
        };

        if (contentType) {
            headers["Content-Type"] =
                "application/json";
        }

        return headers;
    }

    function getItemsByDay() {
        const grouped = new Map();

        for (const item of state.items) {
            const dayItems =
                grouped.get(item.day) || [];

            dayItems.push(item);
            grouped.set(item.day, dayItems);
        }

        return grouped;
    }

    function chooseDefaultDay(itemsByDay) {
        const monthKey = getMonthKey(
            state.currentMonth,
        );

        if (
            state.selectedDay
            && state.selectedDay.startsWith(
                `${monthKey}-`,
            )
        ) {
            return;
        }

        const todayKey = getDayKey(
            new Date(),
        );

        if (todayKey.startsWith(`${monthKey}-`)) {
            state.selectedDay = todayKey;
            return;
        }

        const firstScheduledDay = [
            ...itemsByDay.keys(),
        ].sort()[0];

        state.selectedDay = (
            firstScheduledDay
            || `${monthKey}-01`
        );
    }

    function renderCalendar() {
        const year =
            state.currentMonth.getFullYear();
        const month =
            state.currentMonth.getMonth();

        monthTitle.textContent = (
            `${monthNames[month]} ${year}`
        );

        calendarGrid.replaceChildren();

        const firstWeekday = (
            new Date(year, month, 1).getDay()
            + 6
        ) % 7;

        const daysInMonth = new Date(
            year,
            month + 1,
            0,
        ).getDate();

        const itemsByDay = getItemsByDay();
        chooseDefaultDay(itemsByDay);

        for (
            let index = 0;
            index < firstWeekday;
            index += 1
        ) {
            const spacer =
                document.createElement("span");
            spacer.className =
                "calendar-spacer";
            spacer.setAttribute(
                "aria-hidden",
                "true",
            );
            calendarGrid.append(spacer);
        }

        for (
            let day = 1;
            day <= daysInMonth;
            day += 1
        ) {
            const dayKey = [
                year,
                pad(month + 1),
                pad(day),
            ].join("-");

            const dayItems =
                itemsByDay.get(dayKey) || [];

            const button =
                document.createElement("button");

            button.type = "button";
            button.className = "calendar-day";
            button.dataset.day = dayKey;
            button.setAttribute(
                "aria-label",
                dayItems.length
                    ? (
                        `${day}: публикаций `
                        + dayItems.length
                    )
                    : `${day}: публикаций нет`,
            );

            if (
                dayKey === getDayKey(new Date())
            ) {
                button.classList.add("is-today");
            }

            if (
                dayKey === state.selectedDay
            ) {
                button.classList.add(
                    "is-selected",
                );
            }

            const number =
                document.createElement("span");
            number.className = "day-number";
            number.textContent = String(day);
            button.append(number);

            if (dayItems.length) {
                const marker =
                    document.createElement(
                        "span",
                    );
                marker.className =
                    "publication-marker";
                marker.textContent = String(
                    dayItems.length,
                );
                button.append(marker);
            }

            button.addEventListener(
                "click",
                () => {
                    state.selectedDay = dayKey;
                    renderCalendar();
                    renderSelectedDay();
                },
            );

            calendarGrid.append(button);
        }
    }

    function renderSelectedDay() {
        if (!state.selectedDay) {
            return;
        }

        const dayItems = state.items
            .filter(
                (item) => (
                    item.day
                    === state.selectedDay
                ),
            )
            .sort(
                (left, right) => (
                    left.scheduled_at
                    .localeCompare(
                        right.scheduled_at,
                    )
                ),
            );

        selectedDayTitle.textContent =
            formatSelectedDay(
                state.selectedDay,
            );

        publicationCount.textContent =
            String(dayItems.length);

        publicationList.replaceChildren();

        if (!dayItems.length) {
            const empty =
                document.createElement("p");
            empty.className = "empty-state";
            empty.textContent = (
                "На этот день публикаций нет."
            );
            publicationList.append(empty);
            return;
        }

        for (const item of dayItems) {
            const article =
                document.createElement(
                    "button",
                );
            article.type = "button";
            article.className =
                "publication-card";
            article.addEventListener(
                "click",
                () => openEditor(item.id),
            );

            const time =
                document.createElement("time");
            time.className =
                "publication-time";
            time.dateTime = item.scheduled_at;
            time.textContent = item.time;

            const content =
                document.createElement("div");
            content.className =
                "publication-content";

            const channel =
                document.createElement("h3");
            channel.textContent =
                item.channel_title;

            const meta =
                document.createElement("p");
            meta.className =
                "publication-meta";
            meta.textContent = (
                `${contentTypeIcons[
                    item.content_type
                ] || "•"} `
                + item.content_type_label
                + ` · #${item.id}`
            );

            const preview =
                document.createElement("p");
            preview.className =
                "publication-preview";
            preview.textContent = item.preview;

            const action =
                document.createElement("span");
            action.className =
                "publication-action";
            action.textContent = "Изменить ›";

            content.append(
                channel,
                meta,
                preview,
                action,
            );
            article.append(time, content);
            publicationList.append(article);
        }
    }

    async function loadMonth() {
        if (state.loading) {
            return;
        }

        state.loading = true;
        previousMonthButton.disabled = true;
        nextMonthButton.disabled = true;
        refreshButton.disabled = true;
        setStatus(
            "Загружаем публикации…",
        );

        if (!telegram?.initData) {
            setStatus(
                "Откройте контент-план "
                + "кнопкой внутри Telegram.",
                "error",
            );
            state.loading = false;
            return;
        }

        try {
            const monthKey = getMonthKey(
                state.currentMonth,
            );

            const response = await fetch(
                `/api/content-plan?month=${
                    encodeURIComponent(monthKey)
                }&timezone=${
                    encodeURIComponent(state.timezone)
                }&timezone_offset_minutes=${
                    getTimezoneOffsetMinutes(new Date())
                }`,
                {
                    headers: getAuthHeaders(),
                },
            );

            const payload =
                await response.json();

            if (!response.ok) {
                throw new Error(
                    payload.detail
                    || "Ошибка загрузки.",
                );
            }

            state.items = payload.items;
            state.timezone = payload.timezone;
            timezoneName.textContent =
                formatTimezoneLabel();

            renderCalendar();
            renderSelectedDay();

            setStatus(
                state.items.length
                    ? ""
                    : (
                        "В этом месяце "
                        + "публикаций нет."
                    ),
            );
        } catch (error) {
            setStatus(
                error instanceof Error
                    ? error.message
                    : "Не удалось загрузить план.",
                "error",
            );
        } finally {
            state.loading = false;
            previousMonthButton.disabled = false;
            nextMonthButton.disabled = false;
            refreshButton.disabled = false;
        }
    }

    function setEditorDirty(isDirty) {
        state.editorDirty = isDirty;
        editorDirty.hidden = !isDirty;

        if (!telegram) {
            return;
        }

        if (isDirty) {
            telegram.enableClosingConfirmation?.();
        } else {
            telegram.disableClosingConfirmation?.();
        }
    }

    function confirmDiscardChanges(callback) {
        if (!state.editorDirty) {
            callback();
            return;
        }

        const message = (
            "Есть несохранённые изменения. Закрыть редактор?"
        );

        if (telegram?.showConfirm) {
            telegram.showConfirm(message, (confirmed) => {
                if (confirmed) {
                    callback();
                }
            });
            return;
        }

        if (window.confirm(message)) {
            callback();
        }
    }

    function formatVersionDate(value) {
        if (!value) {
            return "";
        }

        const parsed = new Date(value);

        if (Number.isNaN(parsed.getTime())) {
            return value;
        }

        return new Intl.DateTimeFormat("ru-RU", {
            day: "2-digit",
            month: "2-digit",
            year: "numeric",
            hour: "2-digit",
            minute: "2-digit",
        }).format(parsed);
    }

    function applyHistoricalVersion(item) {
        richEditor.setDocument(
            item.text || "",
            item.text_entities || [],
        );

        const option = [...editorChannel.options].find(
            (candidate) => Number(candidate.value) === Number(item.channel_id),
        );

        if (option) {
            editorChannel.value = option.value;
        }

        const minimum = refreshEditorMinimum();

        if (item.scheduled_local) {
            editorScheduledAt.value = (
                item.scheduled_local >= minimum
                    ? item.scheduled_local
                    : minimum
            );
        }

        editorHistory.hidden = true;
        setEditorDirty(true);
        setEditorStatus(
            `Версия ${item.version} загружена. Нажмите «Сохранить изменения».`,
            "success",
        );
    }

    function renderVersionHistory(items) {
        editorHistoryList.replaceChildren();

        if (!items.length) {
            const empty = document.createElement("p");
            empty.className = "empty-state";
            empty.textContent = "История пока пуста.";
            editorHistoryList.append(empty);
            return;
        }

        for (const item of items) {
            const card = document.createElement("div");
            card.className = "history-item";

            const content = document.createElement("div");
            content.className = "history-item-content";

            const title = document.createElement("strong");
            title.textContent = (
                item.is_current
                    ? `Версия ${item.version} · текущая`
                    : `Версия ${item.version}`
            );

            const meta = document.createElement("span");
            meta.className = "history-item-meta";
            meta.textContent = formatVersionDate(item.created_at);

            const preview = document.createElement("p");
            preview.className = "history-item-preview";
            preview.textContent = (
                (item.text || "Без текста")
                    .replace(/\s+/g, " ")
                    .slice(0, 140)
            );

            content.append(title, meta, preview);
            card.append(content);

            const button = document.createElement("button");
            button.type = "button";
            button.className = "history-load-button";
            button.textContent = item.is_current ? "Текущая" : "Загрузить";
            button.disabled = item.is_current;

            if (!item.is_current) {
                button.addEventListener("click", () => {
                    applyHistoricalVersion(item);
                });
            }

            card.append(button);
            editorHistoryList.append(card);
        }
    }

    async function loadVersionHistory() {
        if (
            state.historyLoading
            || !state.editorPublicationId
        ) {
            return;
        }

        state.historyLoading = true;
        editorHistoryList.textContent = "Загружаем историю…";

        try {
            const response = await fetch(
                `/api/publications/${state.editorPublicationId}/versions`
                + `?timezone=${encodeURIComponent(state.timezone)}`
                + `&timezone_offset_minutes=${getTimezoneOffsetMinutes(new Date())}`,
                { headers: getAuthHeaders() },
            );
            const payload = await response.json();

            if (!response.ok) {
                throw new Error(payload.detail || "Не удалось загрузить историю.");
            }

            renderVersionHistory(payload.items || []);
        } catch (error) {
            editorHistoryList.textContent = (
                error instanceof Error
                    ? error.message
                    : "Не удалось загрузить историю."
            );
        } finally {
            state.historyLoading = false;
        }
    }

    function clearEditorMedia() {
        if (state.mediaObjectUrl) {
            URL.revokeObjectURL(
                state.mediaObjectUrl
            );
            state.mediaObjectUrl = null;
        }

        editorMedia.replaceChildren();
        editorMedia.hidden = true;
    }

    async function loadEditorMedia(
        publicationId,
        contentType,
    ) {
        clearEditorMedia();
        editorHistory.hidden = true;
        editorHistoryList.replaceChildren();

        try {
            const response = await fetch(
                `/api/publications/${
                    publicationId
                }/media`,
                {
                    headers: getAuthHeaders(),
                },
            );

            if (!response.ok) {
                const payload =
                    await response.json();
                throw new Error(
                    payload.detail
                    || (
                        "Не удалось загрузить "
                        + "вложение."
                    ),
                );
            }

            const blob = await response.blob();
            const objectUrl =
                URL.createObjectURL(blob);

            state.mediaObjectUrl = objectUrl;

            const media = (
                contentType === "video"
                    ? document.createElement(
                        "video",
                    )
                    : document.createElement(
                        "img",
                    )
            );

            media.src = objectUrl;
            media.className =
                "editor-media-element";

            if (contentType === "video") {
                media.controls = true;
                media.playsInline = true;
                media.preload = "metadata";
            } else {
                media.alt = (
                    "Вложение публикации"
                );
            }

            editorMedia.append(media);
            editorMedia.hidden = false;
        } catch (error) {
            setEditorStatus(
                error instanceof Error
                    ? error.message
                    : (
                        "Не удалось загрузить "
                        + "вложение."
                    ),
                "error",
            );
        }
    }

    function closeEditor({ force = false } = {}) {
        if (!force && state.editorDirty) {
            confirmDiscardChanges(() => closeEditor({ force: true }));
            return;
        }

        editorOverlay.hidden = true;
        document.body.classList.remove(
            "editor-open",
        );
        state.editorPublicationId = null;
        state.editorVersion = 1;
        clearEditorMedia();
        editorHistory.hidden = true;
        editorHistoryList.replaceChildren();
        richEditor.setDocument("", []);
        setEditorDirty(false);
        setEditorStatus("");
    }

    async function openEditor(
        publicationId,
    ) {
        if (
            state.editorLoading
            || !telegram?.initData
        ) {
            return;
        }

        state.editorLoading = true;
        state.editorPublicationId =
            publicationId;
        editorOverlay.hidden = false;
        document.body.classList.add(
            "editor-open",
        );
        editorSave.disabled = true;
        editorTitle.textContent = (
            `Публикация #${publicationId}`
        );
        setEditorStatus(
            "Загружаем публикацию…",
        );
        clearEditorMedia();

        try {
            const response = await fetch(
                `/api/publications/${
                    publicationId
                }?timezone=${
                    encodeURIComponent(state.timezone)
                }&timezone_offset_minutes=${
                    getTimezoneOffsetMinutes(new Date())
                }`,
                {
                    headers: getAuthHeaders(),
                },
            );
            const payload =
                await response.json();

            if (!response.ok) {
                throw new Error(
                    payload.detail
                    || (
                        "Не удалось загрузить "
                        + "публикацию."
                    ),
                );
            }

            editorType.value =
                payload.content_type_label;
            state.editorContentType = payload.content_type;
            state.editorVersion = payload.version;
            editorVersion.textContent = `Версия ${payload.version}`;
            richEditor.setLimit(
                payload.content_type === "text"
                    ? 4096
                    : 1024,
            );
            richEditor.setDocument(
                payload.text || "",
                payload.text_entities || [],
            );
            const minimum = refreshEditorMinimum();
            editorScheduledAt.value = (
                payload.scheduled_local >= minimum
                    ? payload.scheduled_local
                    : minimum
            );

            editorChannel.replaceChildren();

            for (
                const channel
                of payload.channels
            ) {
                const option =
                    document.createElement(
                        "option",
                    );
                option.value = String(
                    channel.id
                );
                option.textContent =
                    channel.title;
                option.selected = (
                    channel.id
                    === payload.channel_id
                );
                editorChannel.append(option);
            }

            setEditorStatus("");
            setEditorDirty(false);
            editorSave.disabled = false;

            if (payload.has_media) {
                await loadEditorMedia(
                    publicationId,
                    payload.content_type,
                );
            }
        } catch (error) {
            setEditorStatus(
                error instanceof Error
                    ? error.message
                    : (
                        "Не удалось загрузить "
                        + "публикацию."
                    ),
                "error",
            );
        } finally {
            state.editorLoading = false;
        }
    }

    async function saveEditor(event) {
        event.preventDefault();

        if (
            state.editorLoading
            || !state.editorPublicationId
        ) {
            return;
        }

        const minimum = refreshEditorMinimum();

        if (
            !editorScheduledAt.value
            || editorScheduledAt.value < minimum
        ) {
            setEditorStatus(
                "Ближайшее доступное время — следующая минута.",
                "error",
            );
            editorScheduledAt.reportValidity();
            return;
        }

        const editorDocument = richEditor.getDocument();
        const characterCount = Array.from(editorDocument.text).length;
        const maximumLength = (
            state.editorContentType === "text" ? 4096 : 1024
        );

        if (characterCount > maximumLength) {
            setEditorStatus(
                `Текст длиннее допустимого лимита ${maximumLength} символов.`,
                "error",
            );
            return;
        }

        state.editorLoading = true;
        editorSave.disabled = true;
        setEditorStatus(
            "Сохраняем изменения…",
        );

        try {
            const response = await fetch(
                `/api/publications/${
                    state.editorPublicationId
                }`,
                {
                    method: "PATCH",
                    headers: getAuthHeaders(
                        true,
                    ),
                    body: JSON.stringify({
                        channel_id: Number(
                            editorChannel.value
                        ),
                        expected_version: state.editorVersion,
                        text: editorDocument.text,
                        text_entities: editorDocument.entities,
                        scheduled_local: (
                            editorScheduledAt
                            .value
                        ),
                        timezone: state.timezone,
                        timezone_offset_minutes:
                            getTimezoneOffsetMinutes(
                                new Date(
                                    `${
                                        editorScheduledAt.value
                                    }:00`,
                                ),
                            ),
                    }),
                },
            );

            const payload =
                await response.json();

            if (!response.ok) {
                throw new Error(
                    payload.detail
                    || (
                        "Не удалось сохранить "
                        + "изменения."
                    ),
                );
            }

            state.editorVersion = payload.version;
            editorVersion.textContent = `Версия ${payload.version}`;
            setEditorDirty(false);
            setEditorStatus(
                "Изменения сохранены.",
                "success",
            );

            await loadMonth();

            window.setTimeout(
                () => closeEditor({ force: true }),
                500,
            );
        } catch (error) {
            setEditorStatus(
                error instanceof Error
                    ? error.message
                    : (
                        "Не удалось сохранить "
                        + "изменения."
                    ),
                "error",
            );
            editorSave.disabled = false;
        } finally {
            state.editorLoading = false;
        }
    }

    function changeMonth(offset) {
        state.currentMonth = new Date(
            state.currentMonth.getFullYear(),
            state.currentMonth.getMonth()
                + offset,
            1,
        );
        state.selectedDay = null;
        loadMonth();
    }

    previousMonthButton.addEventListener(
        "click",
        () => changeMonth(-1),
    );

    nextMonthButton.addEventListener(
        "click",
        () => changeMonth(1),
    );

    refreshButton.addEventListener(
        "click",
        loadMonth,
    );

    editorClose.addEventListener(
        "click",
        () => closeEditor(),
    );

    editorOverlay.addEventListener(
        "click",
        (event) => {
            if (event.target === editorOverlay) {
                closeEditor();
            }
        },
    );

    editorHistoryToggle.addEventListener(
        "click",
        async () => {
            editorHistory.hidden = !editorHistory.hidden;

            if (!editorHistory.hidden) {
                await loadVersionHistory();
            }
        },
    );

    editorChannel.addEventListener(
        "change",
        () => setEditorDirty(true),
    );

    editorScheduledAt.addEventListener(
        "change",
        () => setEditorDirty(true),
    );

    editorForm.addEventListener(
        "submit",
        saveEditor,
    );

    if (telegram) {
        telegram.ready();
        telegram.expand();
        telegram.BackButton.show();
        telegram.BackButton.onClick(
            () => {
                if (!editorOverlay.hidden) {
                    closeEditor();
                    return;
                }

                telegram.close();
            },
        );
    }

    timezoneName.textContent = formatTimezoneLabel();
    refreshEditorMinimum();
    window.setInterval(
        () => refreshEditorMinimum(),
        15_000,
    );

    loadMonth();
})();
