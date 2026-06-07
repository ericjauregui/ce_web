(function () {
  const form = document.getElementById("checkoutForm");
  const dataScript = document.getElementById("checkoutComboboxData");
  if (!form || !dataScript) return;

  let checkoutData = {};
  try {
    checkoutData = JSON.parse(dataScript.textContent || "{}");
  } catch (_error) {
    return;
  }

  const phoneCountryInput = document.getElementById("checkoutPhoneCountry");
  const phoneCountryCodeInput = document.getElementById(
    "checkoutPhoneCountryCode",
  );
  const phoneInput = document.getElementById("checkoutPhone");
  const phoneError = document.getElementById("checkoutPhoneError");
  const emailInput = document.getElementById("checkoutEmail");
  const emailError = document.getElementById("checkoutEmailError");
  const cityInput = document.getElementById("checkoutCity");
  const cityError = document.getElementById("checkoutCityError");
  const stateInput = document.getElementById("checkoutState");
  const stateError = document.getElementById("checkoutStateError");
  const countryInput = document.getElementById("checkoutCountry");
  const countryKeyInput = document.getElementById("checkoutCountryKey");
  const countryError = document.getElementById("checkoutCountryError");

  const phoneCountryCombobox = document.getElementById(
    "checkoutPhoneCountryCombobox",
  );
  const stateCombobox = document.getElementById("checkoutStateCombobox");
  const countryCombobox = document.getElementById("checkoutCountryCombobox");

  if (
    !phoneCountryInput ||
    !phoneCountryCodeInput ||
    !phoneInput ||
    !phoneError ||
    !emailInput ||
    !emailError ||
    !cityInput ||
    !cityError ||
    !stateInput ||
    !stateError ||
    !countryInput ||
    !countryKeyInput ||
    !countryError ||
    !phoneCountryCombobox ||
    !stateCombobox ||
    !countryCombobox
  ) {
    return;
  }

  const phoneAllowedPattern = /^[0-9()+\-.\s]+$/;
  const phoneInvalidMessage = "Please enter a valid phone number";
  const emailPattern = /^[^\s@]+@[^\s@]+\.[^\s@]+$/;
  const invalidMessage = "Please enter a valid email address";

  const countryLabelByKey = checkoutData.countryLabelByKey || {};
  const phoneCountryDisplayByKey = checkoutData.phoneCountryDisplayByKey || {};
  const subdivisionsByCountryKey = checkoutData.subdivisionsByCountryKey || {};

  function normalizeLookupValue(value) {
    return (value || "")
      .trim()
      .toLowerCase()
      .normalize("NFD")
      .replace(/[\u0300-\u036f]/g, "");
  }

  function setFieldError(input, errorElement, message) {
    errorElement.textContent = message;
    input.classList.toggle("checkout-input-invalid", Boolean(message));
    input.setAttribute("aria-invalid", message ? "true" : "false");
  }

  function setPhoneError(message) {
    phoneError.textContent = message;
    phoneCountryInput.classList.toggle(
      "checkout-input-invalid",
      Boolean(message),
    );
    phoneInput.classList.toggle("checkout-input-invalid", Boolean(message));
    phoneCountryInput.setAttribute("aria-invalid", message ? "true" : "false");
    phoneInput.setAttribute("aria-invalid", message ? "true" : "false");
  }

  function setEmailError(message) {
    emailError.textContent = message;
    emailInput.classList.toggle("checkout-input-invalid", Boolean(message));
    emailInput.setAttribute("aria-invalid", message ? "true" : "false");
  }

  const countryOptions = (checkoutData.countryOptions || []).map(
    function (entry) {
      const key = entry[0];
      const label = entry[1];
      return {
        id: key,
        key,
        label,
        value: label,
        sortLabel: label,
        pinned: key === "us",
        matchTexts: [normalizeLookupValue(label)],
        exactMatches: [normalizeLookupValue(label)],
      };
    },
  );

  const phoneCountryOptions = (checkoutData.phoneCountryOptions || []).map(
    function (entry) {
      const key = entry[0];
      const label = entry[1];
      const dialCode = entry[2];
      const display = phoneCountryDisplayByKey[key] || `${label} (${dialCode})`;
      return {
        id: key,
        key,
        label,
        dialCode,
        value: display,
        sortLabel: label,
        pinned: key === "us",
        matchTexts: [
          normalizeLookupValue(display),
          normalizeLookupValue(label),
          normalizeLookupValue(dialCode),
        ],
        exactMatches: [
          normalizeLookupValue(display),
          normalizeLookupValue(label),
        ],
      };
    },
  );

  const stateOptionsByCountry = {};
  const allStateOptions = [];
  let stateSourceIndex = 0;

  countryOptions.forEach(function (countryOption) {
    const stateNames = subdivisionsByCountryKey[countryOption.key] || [];
    const options = stateNames.map(function (stateName) {
      return {
        id: `${countryOption.key}:${stateName}`,
        key: stateName,
        label: stateName,
        value: stateName,
        sortLabel: stateName,
        sourceIndex: stateSourceIndex++,
        countryKey: countryOption.key,
        countryLabel: countryOption.label,
        matchTexts: [
          normalizeLookupValue(stateName),
          normalizeLookupValue(`${stateName} ${countryOption.label}`),
        ],
      };
    });
    stateOptionsByCountry[countryOption.key] = options;
    allStateOptions.push.apply(allStateOptions, options);
  });

  function compareOptions(left, right) {
    const labelCompare = left.sortLabel.localeCompare(right.sortLabel);
    if (labelCompare !== 0) return labelCompare;
    return (left.countryLabel || "").localeCompare(right.countryLabel || "");
  }

  function getMatchScore(option, query) {
    if (!query) return 0;

    for (let index = 0; index < option.matchTexts.length; index += 1) {
      if (option.matchTexts[index].startsWith(query)) return 0;
    }

    for (let index = 0; index < option.matchTexts.length; index += 1) {
      if (
        option.matchTexts[index].split(/\s+/).some(function (word) {
          return word.startsWith(query);
        })
      ) {
        return 1;
      }
    }

    for (let index = 0; index < option.matchTexts.length; index += 1) {
      if (option.matchTexts[index].includes(query)) return 2;
    }

    return Number.POSITIVE_INFINITY;
  }

  function filterOptions(options, query, config) {
    const settings = config || {};
    const normalizedQuery = normalizeLookupValue(query);
    const limit = settings.limit || 12;

    if (!normalizedQuery && settings.preserveSourceOrderWhenEmpty) {
      return options.slice(0, limit);
    }

    return options
      .map(function (option) {
        return { option, score: getMatchScore(option, normalizedQuery) };
      })
      .filter(function (item) {
        return !normalizedQuery || Number.isFinite(item.score);
      })
      .sort(function (left, right) {
        if (
          settings.pinUnitedStates &&
          left.option.pinned !== right.option.pinned
        ) {
          return left.option.pinned ? -1 : 1;
        }
        if (left.score !== right.score) return left.score - right.score;
        if (settings.preserveSourceOrderOnScore) {
          return (
            (left.option.sourceIndex || 0) - (right.option.sourceIndex || 0)
          );
        }
        return compareOptions(left.option, right.option);
      })
      .slice(0, limit)
      .map(function (item) {
        return item.option;
      });
  }

  function findExactOption(options, value) {
    const normalizedValue = normalizeLookupValue(value);
    if (!normalizedValue) return null;
    return (
      options.find(function (option) {
        return (
          option.exactMatches && option.exactMatches.includes(normalizedValue)
        );
      }) || null
    );
  }

  function createCombobox(config) {
    const wrapper = config.wrapper;
    const input = config.input;
    const menu = config.menu;
    const toggle = wrapper.querySelector(".checkout-combobox__toggle");

    let isOpen = false;
    let activeIndex = -1;
    let currentOptions = [];

    function setExpanded(expanded) {
      isOpen = expanded;
      wrapper.classList.toggle("is-open", expanded);
      input.setAttribute("aria-expanded", expanded ? "true" : "false");
      menu.hidden = !expanded;
      if (!expanded) {
        activeIndex = -1;
        input.removeAttribute("aria-activedescendant");
      }
    }

    function setActiveOption(nextIndex) {
      const boundedIndex =
        nextIndex >= 0 && nextIndex < currentOptions.length ? nextIndex : -1;
      activeIndex = boundedIndex;

      Array.from(menu.querySelectorAll(".checkout-combobox__option")).forEach(
        function (node, index) {
          node.classList.toggle("is-active", index === boundedIndex);
        },
      );

      if (boundedIndex >= 0) {
        const optionId = `${input.id}-option-${boundedIndex}`;
        input.setAttribute("aria-activedescendant", optionId);
        const activeNode = document.getElementById(optionId);
        if (activeNode) {
          activeNode.scrollIntoView({ block: "nearest" });
        }
      } else {
        input.removeAttribute("aria-activedescendant");
      }
    }

    function renderOption(option, index) {
      const button = document.createElement("button");
      button.type = "button";
      button.className = "checkout-combobox__option";
      button.id = `${input.id}-option-${index}`;
      button.setAttribute("role", "option");
      button.dataset.index = String(index);
      button.setAttribute(
        "aria-selected",
        config.isSelectedOption && config.isSelectedOption(option)
          ? "true"
          : "false",
      );

      const textWrap = document.createElement("span");
      textWrap.className = "checkout-combobox__option-text";

      const label = document.createElement("span");
      label.className = "checkout-combobox__option-label";
      label.textContent = config.getOptionLabel(option);
      textWrap.appendChild(label);

      const metaText = config.getOptionMeta ? config.getOptionMeta(option) : "";
      if (metaText) {
        const meta = document.createElement("span");
        meta.className = "checkout-combobox__option-meta";
        meta.textContent = metaText;
        textWrap.appendChild(meta);
      }

      button.appendChild(textWrap);
      if (config.isSelectedOption && config.isSelectedOption(option)) {
        button.classList.add("is-selected");
      }
      return button;
    }

    function renderMenu() {
      currentOptions = config.getOptions(input.value);
      menu.innerHTML = "";

      if (!currentOptions.length) {
        const emptyState = document.createElement("div");
        emptyState.className = "checkout-combobox__empty";
        emptyState.textContent = config.emptyMessage;
        menu.appendChild(emptyState);
      } else {
        currentOptions.forEach(function (option, index) {
          menu.appendChild(renderOption(option, index));
        });
      }

      setExpanded(true);
      setActiveOption(activeIndex);
    }

    function openMenu() {
      renderMenu();
    }

    function closeMenu() {
      setExpanded(false);
    }

    function selectOption(option) {
      config.onSelect(option);
      if (config.onValidate) config.onValidate();
      closeMenu();
    }

    function finalizeInput() {
      config.onInputSync(input.value);
      if (config.commitExactMatchOnBlur !== false) {
        const exactMatch = config.findExactMatch(input.value);
        if (exactMatch) {
          config.onSelect(exactMatch);
        }
      }
    }

    input.addEventListener("focus", openMenu);
    input.addEventListener("input", function () {
      config.onInputSync(input.value);
      openMenu();
    });

    input.addEventListener("keydown", function (event) {
      if (event.key === "ArrowDown") {
        event.preventDefault();
        if (!isOpen) openMenu();
        setActiveOption(
          activeIndex < currentOptions.length - 1 ? activeIndex + 1 : 0,
        );
        return;
      }

      if (event.key === "ArrowUp") {
        event.preventDefault();
        if (!isOpen) openMenu();
        setActiveOption(
          activeIndex > 0 ? activeIndex - 1 : currentOptions.length - 1,
        );
        return;
      }

      if (event.key === "Enter") {
        if (isOpen && activeIndex >= 0 && currentOptions[activeIndex]) {
          event.preventDefault();
          selectOption(currentOptions[activeIndex]);
          return;
        }

        const exactMatch = config.findExactMatch(input.value);
        if (exactMatch) {
          event.preventDefault();
          selectOption(exactMatch);
        }
        return;
      }

      if (event.key === "Escape") {
        closeMenu();
      }
    });

    input.addEventListener("blur", function () {
      window.setTimeout(function () {
        if (wrapper.contains(document.activeElement)) return;
        finalizeInput();
        closeMenu();
      }, 120);
    });

    toggle.addEventListener("mousedown", function (event) {
      event.preventDefault();
    });

    toggle.addEventListener("click", function () {
      if (isOpen) {
        closeMenu();
        return;
      }
      input.focus();
      openMenu();
    });

    menu.addEventListener("pointerdown", function (event) {
      const optionNode = event.target.closest(".checkout-combobox__option");
      if (!optionNode) return;
      event.preventDefault();
      const nextIndex = Number(optionNode.dataset.index);
      if (!Number.isInteger(nextIndex) || !currentOptions[nextIndex]) return;
      selectOption(currentOptions[nextIndex]);
    });

    menu.addEventListener("mousemove", function (event) {
      const optionNode = event.target.closest(".checkout-combobox__option");
      if (!optionNode) return;
      const nextIndex = Number(optionNode.dataset.index);
      if (!Number.isInteger(nextIndex)) return;
      setActiveOption(nextIndex);
    });

    document.addEventListener("pointerdown", function (event) {
      if (wrapper.contains(event.target)) return;
      if (!isOpen) return;
      finalizeInput();
      closeMenu();
    });

    return {
      refresh: function () {
        if (isOpen) {
          renderMenu();
        }
      },
      close: closeMenu,
    };
  }

  function setPhoneCountrySelection(option) {
    phoneCountryInput.value = option.value;
    phoneCountryCodeInput.value = option.key;
  }

  function syncPhoneCountryKey() {
    const exactMatch = findExactOption(
      phoneCountryOptions,
      phoneCountryInput.value,
    );
    phoneCountryCodeInput.value = exactMatch ? exactMatch.key : "";
    if (exactMatch) {
      phoneCountryInput.value = exactMatch.value;
    }
    return phoneCountryCodeInput.value;
  }

  let stateComboboxController = null;

  function setCountrySelection(option) {
    countryInput.value = option.value;
    countryKeyInput.value = option.key;
    if (stateComboboxController) {
      stateComboboxController.refresh();
    }
  }

  function setCountrySelectionByKey(countryKey) {
    const option = countryOptions.find(function (entry) {
      return entry.key === countryKey;
    });
    if (!option) return;
    setCountrySelection(option);
  }

  function syncCountryKey() {
    const exactMatch = findExactOption(countryOptions, countryInput.value);
    countryKeyInput.value = exactMatch ? exactMatch.key : "";
    if (exactMatch) {
      countryInput.value = exactMatch.value;
    }
    if (stateComboboxController) {
      stateComboboxController.refresh();
    }
    return countryKeyInput.value;
  }

  function validatePhoneField() {
    const countryCode = syncPhoneCountryKey();
    const value = phoneInput.value.trim();
    if (!countryCode) {
      setPhoneError("Please select a country code");
      return false;
    }
    if (!value) {
      setPhoneError("Please enter a phone number");
      return false;
    }

    const digitCount = (value.match(/\d/g) || []).length;
    const hasValidChars = phoneAllowedPattern.test(value);
    if (!hasValidChars || digitCount < 7) {
      setPhoneError(phoneInvalidMessage);
      return false;
    }

    setPhoneError("");
    return true;
  }

  function validateEmailField() {
    const value = emailInput.value.trim();
    if (!value) {
      setEmailError("");
      return true;
    }
    if (!emailPattern.test(value)) {
      setEmailError(invalidMessage);
      return false;
    }
    setEmailError("");
    return true;
  }

  function validateCityField() {
    const value = cityInput.value.trim();
    if (!value) {
      setFieldError(cityInput, cityError, "Please enter a city");
      return false;
    }
    setFieldError(cityInput, cityError, "");
    return true;
  }

  function validateStateField() {
    const value = stateInput.value.trim();
    if (!value) {
      setFieldError(stateInput, stateError, "Please enter a state");
      return false;
    }
    stateInput.value = value;
    setFieldError(stateInput, stateError, "");
    return true;
  }

  function validateCountryField() {
    const nextKey = syncCountryKey();
    const value = countryInput.value.trim();
    if (!value) {
      setFieldError(countryInput, countryError, "Please select a country");
      return false;
    }
    if (!nextKey) {
      setFieldError(
        countryInput,
        countryError,
        "Please select a country from the list",
      );
      return false;
    }
    setFieldError(countryInput, countryError, "");
    return true;
  }

  const phoneCountryComboboxController = createCombobox({
    wrapper: phoneCountryCombobox,
    input: phoneCountryInput,
    menu: document.getElementById("checkoutPhoneCountryListbox"),
    emptyMessage: "No matching country codes",
    getOptions: function (query) {
      return filterOptions(phoneCountryOptions, query, {
        limit: 14,
        preserveSourceOrderWhenEmpty: true,
        pinUnitedStates: true,
      });
    },
    getOptionLabel: function (option) {
      return option.label;
    },
    getOptionMeta: function (option) {
      return option.dialCode;
    },
    isSelectedOption: function (option) {
      return phoneCountryCodeInput.value === option.key;
    },
    findExactMatch: function (value) {
      return findExactOption(phoneCountryOptions, value);
    },
    onInputSync: function () {
      syncPhoneCountryKey();
    },
    onSelect: function (option) {
      setPhoneCountrySelection(option);
    },
    onValidate: validatePhoneField,
  });

  const countryComboboxController = createCombobox({
    wrapper: countryCombobox,
    input: countryInput,
    menu: document.getElementById("checkoutCountryListbox"),
    emptyMessage: "No matching countries",
    getOptions: function (query) {
      return filterOptions(countryOptions, query, {
        limit: 14,
        preserveSourceOrderWhenEmpty: true,
        pinUnitedStates: true,
      });
    },
    getOptionLabel: function (option) {
      return option.label;
    },
    isSelectedOption: function (option) {
      return countryKeyInput.value === option.key;
    },
    findExactMatch: function (value) {
      return findExactOption(countryOptions, value);
    },
    onInputSync: function () {
      syncCountryKey();
    },
    onSelect: function (option) {
      setCountrySelection(option);
    },
    onValidate: validateCountryField,
  });

  stateComboboxController = createCombobox({
    wrapper: stateCombobox,
    input: stateInput,
    menu: document.getElementById("checkoutStateListbox"),
    emptyMessage: "No matching states",
    commitExactMatchOnBlur: false,
    getOptions: function (query) {
      const selectedCountryKey = countryKeyInput.value.trim();
      const sourceOptions = selectedCountryKey
        ? stateOptionsByCountry[selectedCountryKey] || []
        : allStateOptions;

      return filterOptions(sourceOptions, query, {
        limit: 14,
        preserveSourceOrderWhenEmpty: true,
        preserveSourceOrderOnScore: true,
      });
    },
    getOptionLabel: function (option) {
      return option.label;
    },
    getOptionMeta: function (option) {
      return countryKeyInput.value ? "" : option.countryLabel;
    },
    isSelectedOption: function (option) {
      return (
        normalizeLookupValue(stateInput.value) ===
        normalizeLookupValue(option.value)
      );
    },
    findExactMatch: function () {
      return null;
    },
    onInputSync: function (value) {
      stateInput.value = value;
    },
    onSelect: function (option) {
      if (!countryKeyInput.value && option.countryKey) {
        setCountrySelectionByKey(option.countryKey);
      }
      stateInput.value = option.value;
    },
    onValidate: validateStateField,
  });

  phoneInput.addEventListener("input", validatePhoneField);
  phoneInput.addEventListener("blur", validatePhoneField);
  emailInput.addEventListener("input", validateEmailField);
  emailInput.addEventListener("blur", validateEmailField);
  cityInput.addEventListener("input", validateCityField);
  cityInput.addEventListener("blur", validateCityField);
  stateInput.addEventListener("input", validateStateField);
  stateInput.addEventListener("blur", validateStateField);
  countryInput.addEventListener("blur", validateCountryField);
  phoneCountryInput.addEventListener("blur", validatePhoneField);

  syncPhoneCountryKey();
  syncCountryKey();

  form.addEventListener("submit", function (event) {
    const requiredFields = form.querySelectorAll("input[required]");
    let missingRequired = false;
    requiredFields.forEach(function (field) {
      if (!field.value.trim()) {
        missingRequired = true;
      }
    });

    const phoneValid = validatePhoneField();
    const emailValid = validateEmailField();
    const cityValid = validateCityField();
    const stateValid = validateStateField();
    const countryValid = validateCountryField();

    if (
      missingRequired ||
      !phoneValid ||
      !emailValid ||
      !cityValid ||
      !stateValid ||
      !countryValid
    ) {
      event.preventDefault();
      phoneCountryComboboxController.close();
      countryComboboxController.close();
      stateComboboxController.close();

      if (!phoneValid) {
        if (!phoneCountryCodeInput.value.trim()) {
          phoneCountryInput.focus();
          return;
        }
        phoneInput.focus();
        return;
      }
      if (!cityValid) {
        cityInput.focus();
        return;
      }
      if (!stateValid) {
        stateInput.focus();
        return;
      }
      if (!countryValid) {
        countryInput.focus();
        return;
      }
      if (!emailValid) {
        emailInput.focus();
      }
    }
  });
})();
