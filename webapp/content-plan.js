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
    const editorMediaCount = document.getElementById(
        "editor-media-count",
    );
    const editorMediaAdd = document.getElementById(
        "editor-media-add",
    );
    const editorMediaInput = document.getElementById(
        "editor-media-input",
    );
    const editorMediaList = document.getElementById(
        "editor-media-list",
    );
    const editorMediaProgress = document.getElementById(
        "editor-media-progress",
    );
    const editorMediaProgressBar = document.getElementById(
        "editor-media-progress-bar",
    );
    const editorMediaProgressText = document.getElementById(
        "editor-media-progress-text",
    );
    const editorShowCaptionAbove = document.getElementById(
        "editor-show-caption-above",
    );
    const editorTelegramPreview = document.getElementById(
        "editor-telegram-preview",
    );
    const editorPreviewMedia = document.getElementById(
        "editor-preview-media",
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
        album: "▦",
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
        editorMediaItems: [],
        editorShowCaptionAbove: false,
        editorMediaMaxItems: 10,
        editorPhotoMaxBytes: 10 * 1024 * 1024,
        editorVideoMaxBytes: 50 * 1024 * 1024,
        editorMediaBusy: false,
        editorMediaObjectUrls: new Map(),
        editorMediaRenderToken: 0,
        draggedMediaId: null,
        pointerDragMediaId: null,
        pointerDragChanged: false,
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

    function formatFileSize(value) {
        const bytes = Number(value || 0);
        if (!bytes) {
            return "размер неизвестен";
        }
        if (bytes < 1024 * 1024) {
            return `${Math.ceil(bytes / 1024)} КБ`;
        }
        return `${(bytes / (1024 * 1024)).toFixed(1)} МБ`;
    }

    function updateEditorVersion(version) {
        state.editorVersion = Number(version);
        editorVersion.textContent = `Версия ${state.editorVersion}`;
    }

    function updateEditorContentType(contentType) {
        state.editorContentType = contentType;
        const labels = {
            text: "Текст",
            photo: "Фотография",
            video: "Видео",
            album: "Альбом",
        };
        editorType.value = labels[contentType] || contentType;
        richEditor.setLimit(contentType === "text" ? 4096 : 1024);
    }

    function setMediaBusy(isBusy) {
        state.editorMediaBusy = isBusy;
        editorMedia.dataset.busy = String(isBusy);
        editorMediaAdd.disabled = (
            isBusy
            || state.editorMediaItems.length >= state.editorMediaMaxItems
        );
        for (const control of editorMediaList.querySelectorAll(
            "button, input, select",
        )) {
            control.disabled = (
                isBusy || control.dataset.boundaryDisabled === "true"
            );
        }
        editorShowCaptionAbove.disabled = (
            isBusy || state.editorMediaItems.length === 0
        );
    }

    function showMediaProgress(value, text) {
        const percent = Math.max(0, Math.min(100, Number(value) || 0));
        editorMediaProgress.hidden = false;
        editorMediaProgressBar.style.width = `${percent}%`;
        editorMediaProgressText.textContent = text;
    }

    function hideMediaProgress() {
        editorMediaProgress.hidden = true;
        editorMediaProgressBar.style.width = "0%";
        editorMediaProgressText.textContent = "Подготовка…";
    }

    function revokeEditorMediaUrls() {
        for (const objectUrl of state.editorMediaObjectUrls.values()) {
            URL.revokeObjectURL(objectUrl);
        }
        state.editorMediaObjectUrls.clear();
    }

    function resetEditorMedia() {
        state.editorMediaRenderToken += 1;
        revokeEditorMediaUrls();
        state.editorMediaItems = [];
        state.draggedMediaId = null;
        state.pointerDragMediaId = null;
        state.pointerDragChanged = false;
        editorMediaList.replaceChildren();
        editorPreviewMedia.replaceChildren();
        editorPreviewMedia.hidden = true;
        state.editorShowCaptionAbove = false;
        editorShowCaptionAbove.checked = false;
        editorTelegramPreview.dataset.captionAbove = "false";
        editorMediaCount.textContent = `0 / ${state.editorMediaMaxItems}`;
        hideMediaProgress();
        setMediaBusy(false);
    }

    function applyMediaPayload(payload, { render = true } = {}) {
        updateEditorVersion(payload.version);
        updateEditorContentType(payload.content_type);
        state.editorMediaItems = [...(payload.media || [])].sort(
            (left, right) => left.position - right.position,
        );
        if (typeof payload.show_caption_above_media === "boolean") {
            state.editorShowCaptionAbove = payload.show_caption_above_media;
        }
        if (render) {
            renderMediaManager();
        }
    }

    async function fetchMediaObjectUrl(item, renderToken) {
        const response = await fetch(item.preview_url, {
            headers: getAuthHeaders(),
        });
        if (!response.ok) {
            let detail = "Не удалось загрузить превью.";
            try {
                const payload = await response.json();
                detail = payload.detail || detail;
            } catch {
                // Response is not JSON.
            }
            throw new Error(detail);
        }
        const objectUrl = URL.createObjectURL(await response.blob());
        if (renderToken !== state.editorMediaRenderToken) {
            URL.revokeObjectURL(objectUrl);
            return null;
        }
        state.editorMediaObjectUrls.set(item.id, objectUrl);
        return objectUrl;
    }

    function createMediaElement(item, objectUrl, { preview = false } = {}) {
        const element = document.createElement(
            item.media_type === "video" ? "video" : "img",
        );
        element.src = objectUrl;
        if (item.media_type === "video") {
            element.playsInline = true;
            element.preload = "metadata";
            element.muted = preview;
            element.controls = !preview;
        } else {
            element.alt = `Вложение ${item.position}: ${item.original_filename}`;
        }
        return element;
    }

    function renderTelegramMediaPreview() {
        editorPreviewMedia.replaceChildren();
        const items = state.editorMediaItems;
        const hasMedia = items.length > 0;
        editorPreviewMedia.hidden = !hasMedia;
        editorShowCaptionAbove.disabled = state.editorMediaBusy || !hasMedia;
        editorTelegramPreview.dataset.captionAbove = String(
            hasMedia && editorShowCaptionAbove.checked,
        );

        if (!hasMedia) {
            return;
        }

        const visibleItems = items.slice(0, 4);
        editorPreviewMedia.dataset.count = (
            items.length === 1
                ? "1"
                : items.length <= 4
                    ? String(items.length)
                    : "many"
        );

        visibleItems.forEach((item, index) => {
            const container = document.createElement("div");
            container.className = "telegram-media-preview-item";
            const objectUrl = state.editorMediaObjectUrls.get(item.id);
            if (objectUrl) {
                container.append(createMediaElement(item, objectUrl, { preview: true }));
            } else {
                const placeholder = document.createElement("span");
                placeholder.className = "media-thumb-placeholder";
                placeholder.textContent = item.media_type === "video" ? "Видео" : "Фото";
                container.append(placeholder);
            }
            if (items.length > 4 && index === 3) {
                const more = document.createElement("span");
                more.className = "telegram-media-preview-more";
                more.textContent = `+${items.length - 3}`;
                container.append(more);
            }
            editorPreviewMedia.append(container);
        });
    }

    function mediaOrderFromDom() {
        return [...editorMediaList.querySelectorAll(".media-card")]
            .map((card) => Number(card.dataset.mediaId))
            .filter(Number.isInteger);
    }

    function positionMediaCard(draggedCard, targetCard, clientY) {
        if (!draggedCard || !targetCard || draggedCard === targetCard) {
            return false;
        }
        const rectangle = targetCard.getBoundingClientRect();
        const after = clientY > rectangle.top + rectangle.height / 2;
        editorMediaList.insertBefore(
            draggedCard,
            after ? targetCard.nextSibling : targetCard,
        );
        return true;
    }

    async function parseJsonResponse(response) {
        let payload = {};
        try {
            payload = await response.json();
        } catch {
            // Keep empty payload for non-JSON errors.
        }
        if (!response.ok) {
            throw new Error(payload.detail || `Ошибка HTTP ${response.status}.`);
        }
        return payload;
    }

    function getClientMediaContentType(file) {
        if (file.type) {
            return file.type.toLowerCase();
        }
        const filename = file.name.toLowerCase();
        if (filename.endsWith(".jpg") || filename.endsWith(".jpeg")) {
            return "image/jpeg";
        }
        if (filename.endsWith(".png")) {
            return "image/png";
        }
        if (filename.endsWith(".mp4")) {
            return "video/mp4";
        }
        return "";
    }

    function uploadRawMedia(file, { mediaId = null, progressLabel = "Загрузка" } = {}) {
        return new Promise((resolve, reject) => {
            const method = mediaId === null ? "POST" : "PUT";
            const suffix = mediaId === null ? "media" : `media/${mediaId}`;
            const request = new XMLHttpRequest();
            request.open(
                method,
                `/api/publications/${state.editorPublicationId}/${suffix}`,
            );
            request.responseType = "json";
            request.setRequestHeader(
                "X-Telegram-Init-Data",
                telegram?.initData || "",
            );
            request.setRequestHeader("X-Expected-Version", String(state.editorVersion));
            request.setRequestHeader("X-File-Name", encodeURIComponent(file.name));
            request.setRequestHeader(
                "Content-Type",
                getClientMediaContentType(file) || "application/octet-stream",
            );
            request.upload.addEventListener("progress", (event) => {
                if (!event.lengthComputable) {
                    showMediaProgress(10, `${progressLabel}: ${file.name}`);
                    return;
                }
                showMediaProgress(
                    Math.round((event.loaded / event.total) * 100),
                    `${progressLabel}: ${file.name}`,
                );
            });
            request.addEventListener("load", () => {
                const payload = request.response || {};
                if (request.status < 200 || request.status >= 300) {
                    reject(new Error(payload.detail || `Ошибка HTTP ${request.status}.`));
                    return;
                }
                resolve(payload);
            });
            request.addEventListener("error", () => {
                reject(new Error("Сеть прервала загрузку вложения."));
            });
            request.addEventListener("abort", () => {
                reject(new Error("Загрузка вложения отменена."));
            });
            request.send(file);
        });
    }

    function validateClientMediaFile(file) {
        const contentType = getClientMediaContentType(file);
        const supported = new Set(["image/jpeg", "image/png", "video/mp4"]);
        if (!supported.has(contentType)) {
            throw new Error(`Файл «${file.name}»: поддерживаются JPEG, PNG и MP4.`);
        }
        const maximum = contentType === "video/mp4"
            ? state.editorVideoMaxBytes
            : state.editorPhotoMaxBytes;
        if (file.size > maximum) {
            throw new Error(
                `Файл «${file.name}» больше лимита ${formatFileSize(maximum)}.`,
            );
        }
    }

    async function addMediaFiles(fileList) {
        const files = [...fileList];
        if (!files.length || state.editorMediaBusy) {
            return;
        }
        const available = state.editorMediaMaxItems - state.editorMediaItems.length;
        if (files.length > available) {
            setEditorStatus(
                `Можно добавить ещё ${available} вложений. Максимум — ${state.editorMediaMaxItems}.`,
                "error",
            );
            return;
        }
        try {
            files.forEach(validateClientMediaFile);
        } catch (error) {
            setEditorStatus(error.message, "error");
            return;
        }

        setMediaBusy(true);
        let completed = 0;
        try {
            for (const file of files) {
                const payload = await uploadRawMedia(file, {
                    progressLabel: `Файл ${completed + 1} из ${files.length}`,
                });
                applyMediaPayload(payload, { render: false });
                completed += 1;
            }
            renderMediaManager();
            setEditorStatus(
                files.length === 1
                    ? "Вложение добавлено и сохранено."
                    : `Добавлено и сохранено вложений: ${files.length}.`,
                "success",
            );
        } catch (error) {
            renderMediaManager();
            setEditorStatus(
                completed
                    ? `${error.message} Успешно добавлено до ошибки: ${completed}.`
                    : error.message,
                "error",
            );
        } finally {
            editorMediaInput.value = "";
            hideMediaProgress();
            setMediaBusy(false);
        }
    }

    async function replaceMediaFile(mediaId, file) {
        if (!file || state.editorMediaBusy) {
            return;
        }
        try {
            validateClientMediaFile(file);
        } catch (error) {
            setEditorStatus(error.message, "error");
            return;
        }
        setMediaBusy(true);
        try {
            const payload = await uploadRawMedia(file, {
                mediaId,
                progressLabel: "Замена",
            });
            applyMediaPayload(payload);
            setEditorStatus("Вложение заменено и сохранено.", "success");
        } catch (error) {
            setEditorStatus(error.message, "error");
        } finally {
            hideMediaProgress();
            setMediaBusy(false);
        }
    }

    function askConfirmation(message) {
        return new Promise((resolve) => {
            if (telegram?.showConfirm) {
                telegram.showConfirm(message, resolve);
                return;
            }
            resolve(window.confirm(message));
        });
    }

    async function deleteMediaItem(mediaId) {
        if (state.editorMediaBusy) {
            return;
        }
        const confirmed = await askConfirmation(
            "Удалить вложение из публикации? Файл в хранилище также будет удалён.",
        );
        if (!confirmed) {
            return;
        }
        setMediaBusy(true);
        try {
            const response = await fetch(
                `/api/publications/${state.editorPublicationId}/media/${mediaId}`
                + `?expected_version=${state.editorVersion}`,
                {
                    method: "DELETE",
                    headers: getAuthHeaders(),
                },
            );
            applyMediaPayload(await parseJsonResponse(response));
            setEditorStatus("Вложение удалено.", "success");
        } catch (error) {
            setEditorStatus(error.message, "error");
        } finally {
            setMediaBusy(false);
        }
    }

    async function saveMediaOrder(mediaIds) {
        const current = state.editorMediaItems.map((item) => item.id);
        if (
            mediaIds.length !== current.length
            || mediaIds.every((mediaId, index) => mediaId === current[index])
            || state.editorMediaBusy
        ) {
            renderMediaManager();
            return;
        }
        setMediaBusy(true);
        try {
            const response = await fetch(
                `/api/publications/${state.editorPublicationId}/media/order`,
                {
                    method: "PATCH",
                    headers: getAuthHeaders(true),
                    body: JSON.stringify({
                        expected_version: state.editorVersion,
                        media_ids: mediaIds,
                    }),
                },
            );
            applyMediaPayload(await parseJsonResponse(response));
            setEditorStatus("Порядок вложений сохранён.", "success");
        } catch (error) {
            renderMediaManager();
            setEditorStatus(error.message, "error");
        } finally {
            setMediaBusy(false);
        }
    }

    async function saveMediaOptions({
        mediaId = null,
        hasSpoiler = null,
        showCaptionAbove = null,
    }) {
        if (state.editorMediaBusy) {
            return;
        }
        const previousCaptionAbove = state.editorShowCaptionAbove;
        if (showCaptionAbove !== null) {
            state.editorShowCaptionAbove = showCaptionAbove;
        }
        setMediaBusy(true);
        try {
            const response = await fetch(
                `/api/publications/${state.editorPublicationId}/media/options`,
                {
                    method: "PATCH",
                    headers: getAuthHeaders(true),
                    body: JSON.stringify({
                        expected_version: state.editorVersion,
                        media_id: mediaId,
                        has_spoiler: hasSpoiler,
                        show_caption_above_media: showCaptionAbove,
                    }),
                },
            );
            const payload = await parseJsonResponse(response);
            if (showCaptionAbove !== null) {
                payload.show_caption_above_media = showCaptionAbove;
            }
            applyMediaPayload(payload);
            setEditorStatus("Параметры вложений сохранены.", "success");
        } catch (error) {
            state.editorShowCaptionAbove = previousCaptionAbove;
            renderMediaManager();
            setEditorStatus(error.message, "error");
        } finally {
            setMediaBusy(false);
        }
    }

    function makeMediaActionButton(text, title, callback, kind = "") {
        const button = document.createElement("button");
        button.type = "button";
        button.className = "media-action-button";
        button.textContent = text;
        button.title = title;
        if (kind) {
            button.dataset.kind = kind;
        }
        button.addEventListener("click", callback);
        return button;
    }

    function createMediaCard(item, index, renderToken) {
        const card = document.createElement("article");
        card.className = "media-card";
        card.dataset.mediaId = String(item.id);
        card.draggable = true;

        const handle = document.createElement("button");
        handle.type = "button";
        handle.className = "media-drag-handle";
        handle.textContent = "⠿";
        handle.title = "Перетащить вложение";
        handle.setAttribute("aria-label", `Перетащить вложение ${index + 1}`);

        const thumb = document.createElement("div");
        thumb.className = "media-thumb";
        const placeholder = document.createElement("span");
        placeholder.className = "media-thumb-placeholder";
        placeholder.textContent = "Загрузка…";
        thumb.append(placeholder);

        const positionBadge = document.createElement("span");
        positionBadge.className = "media-position-badge";
        positionBadge.textContent = `#${index + 1}`;
        thumb.append(positionBadge);
        if (item.has_spoiler) {
            const spoilerBadge = document.createElement("span");
            spoilerBadge.className = "media-spoiler-badge";
            spoilerBadge.textContent = "Спойлер";
            thumb.append(spoilerBadge);
        }

        const body = document.createElement("div");
        body.className = "media-card-body";
        const heading = document.createElement("div");
        heading.className = "media-card-heading";
        const title = document.createElement("strong");
        title.className = "media-card-title";
        title.textContent = item.original_filename;
        title.title = item.original_filename;
        heading.append(title);

        const meta = document.createElement("p");
        meta.className = "media-card-meta";
        meta.textContent = `${item.media_type === "video" ? "Видео" : "Фото"} · ${formatFileSize(item.file_size)}`;

        const order = document.createElement("div");
        order.className = "media-card-order";
        const up = makeMediaActionButton("↑", "Переместить выше", () => {
            const ids = state.editorMediaItems.map((media) => media.id);
            const currentIndex = ids.indexOf(item.id);
            if (currentIndex > 0) {
                [ids[currentIndex - 1], ids[currentIndex]] = [
                    ids[currentIndex],
                    ids[currentIndex - 1],
                ];
                saveMediaOrder(ids);
            }
        });
        up.dataset.boundaryDisabled = String(index === 0);
        up.disabled = index === 0;
        const down = makeMediaActionButton("↓", "Переместить ниже", () => {
            const ids = state.editorMediaItems.map((media) => media.id);
            const currentIndex = ids.indexOf(item.id);
            if (currentIndex < ids.length - 1) {
                [ids[currentIndex], ids[currentIndex + 1]] = [
                    ids[currentIndex + 1],
                    ids[currentIndex],
                ];
                saveMediaOrder(ids);
            }
        });
        down.dataset.boundaryDisabled = String(
            index === state.editorMediaItems.length - 1,
        );
        down.disabled = index === state.editorMediaItems.length - 1;
        const position = document.createElement("select");
        position.className = "media-position-select";
        position.setAttribute("aria-label", `Позиция вложения ${index + 1}`);
        state.editorMediaItems.forEach((_, positionIndex) => {
            const option = document.createElement("option");
            option.value = String(positionIndex + 1);
            option.textContent = `№ ${positionIndex + 1}`;
            option.selected = positionIndex === index;
            position.append(option);
        });
        position.addEventListener("change", () => {
            const ids = state.editorMediaItems.map((media) => media.id);
            const from = ids.indexOf(item.id);
            const to = Number(position.value) - 1;
            ids.splice(to, 0, ids.splice(from, 1)[0]);
            saveMediaOrder(ids);
        });
        order.append(up, down, position);

        const actions = document.createElement("div");
        actions.className = "media-card-actions";
        const replaceInput = document.createElement("input");
        replaceInput.type = "file";
        replaceInput.accept = "image/jpeg,image/png,video/mp4";
        replaceInput.hidden = true;
        replaceInput.addEventListener("change", () => {
            const [file] = replaceInput.files || [];
            replaceMediaFile(item.id, file);
            replaceInput.value = "";
        });
        const replace = makeMediaActionButton("Заменить", "Заменить файл", () => {
            replaceInput.click();
        });
        const remove = makeMediaActionButton(
            "Удалить",
            "Удалить вложение",
            () => deleteMediaItem(item.id),
            "danger",
        );
        const spoilerLabel = document.createElement("label");
        spoilerLabel.className = "media-inline-option";
        const spoiler = document.createElement("input");
        spoiler.type = "checkbox";
        spoiler.checked = Boolean(item.has_spoiler);
        spoiler.addEventListener("change", () => {
            saveMediaOptions({ mediaId: item.id, hasSpoiler: spoiler.checked });
        });
        spoilerLabel.append(spoiler, document.createTextNode("Спойлер"));
        actions.append(replaceInput, replace, remove, spoilerLabel);

        body.append(heading, meta, order, actions);
        card.append(handle, thumb, body);

        card.addEventListener("dragstart", (event) => {
            state.draggedMediaId = item.id;
            card.dataset.dragging = "true";
            event.dataTransfer.effectAllowed = "move";
            event.dataTransfer.setData("text/plain", String(item.id));
        });
        card.addEventListener("dragover", (event) => {
            event.preventDefault();
            const dragged = editorMediaList.querySelector(
                `[data-media-id="${state.draggedMediaId}"]`,
            );
            if (positionMediaCard(dragged, card, event.clientY)) {
                card.dataset.dragTarget = "true";
            }
        });
        card.addEventListener("dragleave", () => {
            delete card.dataset.dragTarget;
        });
        card.addEventListener("drop", (event) => {
            event.preventDefault();
            delete card.dataset.dragTarget;
        });
        card.addEventListener("dragend", () => {
            delete card.dataset.dragging;
            for (const target of editorMediaList.querySelectorAll("[data-drag-target]")) {
                delete target.dataset.dragTarget;
            }
            state.draggedMediaId = null;
            saveMediaOrder(mediaOrderFromDom());
        });

        handle.addEventListener("pointerdown", (event) => {
            if (event.pointerType === "mouse") {
                return;
            }
            event.preventDefault();
            state.pointerDragMediaId = item.id;
            state.pointerDragChanged = false;
            card.dataset.dragging = "true";
            handle.setPointerCapture?.(event.pointerId);
        });
        handle.addEventListener("pointermove", (event) => {
            if (state.pointerDragMediaId !== item.id) {
                return;
            }
            event.preventDefault();
            const target = document.elementFromPoint(event.clientX, event.clientY)
                ?.closest(".media-card");
            if (target && positionMediaCard(card, target, event.clientY)) {
                state.pointerDragChanged = true;
            }
        });
        const finishPointerDrag = (event) => {
            if (state.pointerDragMediaId !== item.id) {
                return;
            }
            handle.releasePointerCapture?.(event.pointerId);
            delete card.dataset.dragging;
            state.pointerDragMediaId = null;
            if (state.pointerDragChanged) {
                saveMediaOrder(mediaOrderFromDom());
            }
            state.pointerDragChanged = false;
        };
        handle.addEventListener("pointerup", finishPointerDrag);
        handle.addEventListener("pointercancel", finishPointerDrag);

        fetchMediaObjectUrl(item, renderToken)
            .then((objectUrl) => {
                if (!objectUrl || renderToken !== state.editorMediaRenderToken) {
                    return;
                }
                const mediaElement = createMediaElement(item, objectUrl);
                const updateTechnicalMeta = () => {
                    const dimensions = (
                        item.media_type === "video"
                            ? (
                                mediaElement.videoWidth && mediaElement.videoHeight
                                    ? `${mediaElement.videoWidth}×${mediaElement.videoHeight}`
                                    : ""
                            )
                            : (
                                mediaElement.naturalWidth && mediaElement.naturalHeight
                                    ? `${mediaElement.naturalWidth}×${mediaElement.naturalHeight}`
                                    : ""
                            )
                    );
                    const duration = (
                        item.media_type === "video" && Number.isFinite(mediaElement.duration)
                            ? `${Math.floor(mediaElement.duration / 60)}:${pad(
                                Math.floor(mediaElement.duration % 60),
                            )}`
                            : ""
                    );
                    meta.textContent = [
                        item.media_type === "video" ? "Видео" : "Фото",
                        formatFileSize(item.file_size),
                        dimensions,
                        duration,
                    ].filter(Boolean).join(" · ");
                };
                mediaElement.addEventListener(
                    item.media_type === "video" ? "loadedmetadata" : "load",
                    updateTechnicalMeta,
                    { once: true },
                );
                placeholder.replaceWith(mediaElement);
                renderTelegramMediaPreview();
            })
            .catch((error) => {
                placeholder.textContent = "Превью недоступно";
                placeholder.title = error.message;
            });

        return card;
    }

    function renderMediaManager() {
        state.editorMediaRenderToken += 1;
        const renderToken = state.editorMediaRenderToken;
        revokeEditorMediaUrls();
        editorMediaList.replaceChildren();
        editorMediaCount.textContent = (
            `${state.editorMediaItems.length} / ${state.editorMediaMaxItems}`
        );
        editorShowCaptionAbove.checked = state.editorShowCaptionAbove;

        if (!state.editorMediaItems.length) {
            const empty = document.createElement("p");
            empty.className = "media-empty-state";
            empty.textContent = (
                "Вложений нет. Добавьте фото или видео, и текстовая публикация "
                + "автоматически станет медиапубликацией."
            );
            editorMediaList.append(empty);
        } else {
            state.editorMediaItems.forEach((item, index) => {
                editorMediaList.append(createMediaCard(item, index, renderToken));
            });
        }

        renderTelegramMediaPreview();
        setMediaBusy(state.editorMediaBusy);
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
        resetEditorMedia();
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
        resetEditorMedia();

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

            state.editorMediaMaxItems = payload.media_max_items || 10;
            state.editorPhotoMaxBytes = (
                payload.media_photo_max_bytes || 10 * 1024 * 1024
            );
            state.editorVideoMaxBytes = (
                payload.media_video_max_bytes || 50 * 1024 * 1024
            );
            updateEditorContentType(payload.content_type);
            updateEditorVersion(payload.version);
            state.editorMediaItems = [...(payload.media || [])].sort(
                (left, right) => left.position - right.position,
            );
            state.editorShowCaptionAbove = Boolean(
                payload.show_caption_above_media,
            );
            renderMediaManager();
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
                        show_caption_above_media:
                            editorShowCaptionAbove.checked,
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

    editorMediaAdd.addEventListener("click", () => {
        if (!state.editorMediaBusy) {
            editorMediaInput.click();
        }
    });

    editorMediaInput.addEventListener("change", () => {
        addMediaFiles(editorMediaInput.files || []);
    });

    editorShowCaptionAbove.addEventListener("change", () => {
        if (!state.editorMediaItems.length) {
            editorShowCaptionAbove.checked = false;
            return;
        }
        const requestedValue = editorShowCaptionAbove.checked;
        state.editorShowCaptionAbove = requestedValue;
        renderTelegramMediaPreview();
        saveMediaOptions({
            showCaptionAbove: requestedValue,
        });
    });

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
