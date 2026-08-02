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

    const state = {
        currentMonth: new Date(
            new Date().getFullYear(),
            new Date().getMonth(),
            1,
        ),
        selectedDay: null,
        items: [],
        timezone: "—",
        loading: false,
    };

    function pad(value) {
        return String(value).padStart(2, "0");
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
                    "article",
                );
            article.className =
                "publication-card";

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

            content.append(
                channel,
                meta,
                preview,
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
                }`,
                {
                    headers: {
                        "X-Telegram-Init-Data":
                            telegram.initData,
                    },
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
                state.timezone;

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

    if (telegram) {
        telegram.ready();
        telegram.expand();
        telegram.BackButton.show();
        telegram.BackButton.onClick(
            () => telegram.close(),
        );
    }

    loadMonth();
})();
