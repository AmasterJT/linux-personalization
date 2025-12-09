document.addEventListener("DOMContentLoaded", function () {
  const checkElement = setInterval(() => {
    const commandDialog = document.querySelector(".quick-input-widget");
    if (commandDialog) {
      if (commandDialog.style.display !== "none") {
        runMyScript();
      }
      
      const observer = new MutationObserver((mutations) => {
        mutations.forEach((mutation) => {
          if (
            mutation.type === "attributes" &&
            mutation.attributeName === "style"
          ) {
            if (commandDialog.style.display === "none") {
              handleEscape();
            } else {
              runMyScript();
            }
          }
        });
      });

      observer.observe(commandDialog, { attributes: true });
      clearInterval(checkElement);
    } else {
      console.log("Command dialog not found yet. Retrying...");
    }
  }, 500);

  document.addEventListener("keydown", function (event) {
    if ((event.metaKey || event.ctrlKey) && event.key === "p") {
      event.preventDefault();
      runMyScript();
    } else if (event.key === "Escape" || event.key === "Esc") {
      event.preventDefault();
      handleEscape();
    }
  });

  document.addEventListener(
    "keydown",
    function (event) {
      if (event.key === "Escape" || event.key === "Esc") {
        handleEscape();
      }
    },
    true
  );

  function runMyScript() {
    const targetDiv = document.querySelector(".monaco-workbench");
    const existingElement = document.getElementById("command-blur");
    if (existingElement) {
      existingElement.remove();
    }

    const newElement = document.createElement("div");
    newElement.setAttribute("id", "command-blur");
    newElement.style.position = "absolute";
    newElement.style.top = "0";
    newElement.style.left = "0";
    newElement.style.width = "100%";
    newElement.style.height = "100%";
    newElement.style.backdropFilter = "blur(10px)";
    newElement.style.zIndex = "1000";

    newElement.addEventListener("click", function () {
      newElement.remove();
    });

    targetDiv.appendChild(newElement);
    
    // Excluir la clase sticky-widget-lines-scrollable del desenfoque
    const stickyWidget = document.querySelector(".sticky-widget-lines-scrollable");
    if (stickyWidget) {
      stickyWidget.style.backdropFilter = "none";
    }
  }

  function handleEscape() {
    const element = document.getElementById("command-blur");
    if (element) {
      element.click();
    }
  }
});
