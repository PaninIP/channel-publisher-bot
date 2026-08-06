(() => {
    const telegram = window.Telegram?.WebApp;

    const input = document.getElementById("schedule-at");
    const timezoneElement = document.getElementById(
        "timezone-name",
    );
    const validationElement = document.getElementById(
        "validation-message",
    );
    const fallbackButton = document.getElementById(
        "fallback-submit",
    );

    const timezone = (
        Intl.DateTimeFormat()
            .resolvedOptions()
            .timeZone || ""
    ).trim();

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

    function formatTimezoneLabel(date) {
        const offsetMinutes = getTimezoneOffsetMinutes(date);
        const sign = offsetMinutes >= 0 ? "+" : "-";
        const absoluteMinutes = Math.abs(offsetMinutes);
        const hours = Math.floor(absoluteMinutes / 60);
        const minutes = absoluteMinutes % 60;
        const offset = (
            `UTC${sign}${pad(hours)}:${pad(minutes)}`
        );

        return timezone
            ? `${timezone} (${offset})`
            : offset;
    }

    function refreshMinimum({ forceValue = false } = {}) {
        const minimum = formatLocalDateTime(
            getNextAvailableMinute(),
        );

        input.min = minimum;

        if (
            forceValue
            || !input.value
            || input.value < minimum
        ) {
            input.value = minimum;
        }

        return minimum;
    }

    function selectedValueIsValid() {
        const minimum = refreshMinimum();
        const value = input.value;

        if (!value) {
            validationElement.textContent =
                "Выберите дату и время.";
            return false;
        }

        if (value < minimum) {
            validationElement.textContent = (
                "Ближайшее доступное время — "
                + "следующая минута."
            );
            return false;
        }

        validationElement.textContent = "";
        return true;
    }

    function updateControls() {
        const isValid = selectedValueIsValid();

        fallbackButton.disabled = !isValid;

        if (!telegram) {
            return;
        }

        telegram.MainButton.setText("Запланировать");

        if (isValid) {
            telegram.MainButton.show();
            telegram.MainButton.enable();
        } else {
            telegram.MainButton.hide();
        }
    }

    function submit() {
        if (!selectedValueIsValid()) {
            return;
        }

        const selectedDate = new Date(
            `${input.value}:00`,
        );
        const payload = JSON.stringify({
            action: "schedule_publication",
            scheduled_local: input.value,
            timezone,
            timezone_offset_minutes:
                getTimezoneOffsetMinutes(selectedDate),
        });

        if (!telegram) {
            validationElement.textContent =
                "Откройте приложение внутри Telegram.";
            return;
        }

        telegram.sendData(payload);
        telegram.close();
    }

    timezoneElement.textContent = formatTimezoneLabel(
        new Date(),
    );
    refreshMinimum({ forceValue: true });

    input.addEventListener("change", updateControls);
    input.addEventListener("input", updateControls);

    fallbackButton.addEventListener(
        "click",
        submit,
    );

    if (telegram) {
        telegram.ready();
        telegram.expand();
        telegram.MainButton.onClick(submit);
    }

    window.setInterval(updateControls, 15_000);
    updateControls();
})();
