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

    const params = new URLSearchParams(
        window.location.search,
    );

    const timezone = (
        params.get("timezone") || "Europe/Moscow"
    ).trim();

    const minimumLocal = params.get("min_local") || "";

    timezoneElement.textContent = timezone;

    if (minimumLocal) {
        input.min = minimumLocal;
        input.value = minimumLocal;
    }

    function selectedValueIsValid() {
        const value = input.value;

        if (!value) {
            validationElement.textContent =
                "???????? ???? ? ?????.";
            return false;
        }

        if (minimumLocal && value < minimumLocal) {
            validationElement.textContent =
                "????????? ????? ??? ??????.";
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

        telegram.MainButton.setText("?????????????");

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

        const payload = JSON.stringify({
            action: "schedule_publication",
            scheduled_local: input.value,
            timezone,
        });

        if (!telegram) {
            validationElement.textContent =
                "???????? ???????? ?????? Telegram.";
            return;
        }

        telegram.sendData(payload);
        telegram.close();
    }

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

    updateControls();
})();
