(function () {
  const departments = [
    {
      label: "After Sales",
      base: "/aftersales",
      links: [
        ["Dashboard", "/aftersales"],
        ["Service Calls", "/aftersales/service-calls"],
        ["Spare Parts", "/aftersales/spare-parts"],
        ["Preventive Maintenance", "/aftersales/pm"],
        ["Contracts", "/aftersales/contracts"],
        ["Reports", "/aftersales/pm/reports"],
      ],
    },
    {
      label: "Sales",
      base: "/sales",
      links: [
        ["Dashboard", "/sales"],
        ["Quotations", "/sales/quotations"],
        ["Customer Orders", "/sales/customer-orders"],
        ["Products", "/sales/products"],
        ["Reports", "/sales/reports"],
      ],
    },
    {
      label: "Procurement",
      base: "/procurement",
      links: [
        ["Dashboard", "/procurement"],
        ["Purchase Orders", "/procurement/purchase-orders"],
        ["Suppliers", "/procurement/suppliers"],
        ["Shipments", "/procurement/shipments"],
        ["Reports", "/procurement/reports"],
      ],
    },
    {
      label: "Warehouse",
      base: "/warehouse",
      links: [
        ["Dashboard", "/warehouse"],
        ["Stock Items", "/warehouse/stock-items"],
        ["Receptions", "/warehouse/receptions"],
        ["Delivery Orders", "/warehouse/delivery-orders"],
        ["Stock Movement", "/warehouse/stock-movement"],
        ["Inventory Count", "/warehouse/inventory-count"],
      ],
    },
    {
      label: "Finance",
      base: "/finance",
      links: [
        ["Dashboard", "/finance"],
        ["Invoices", "/finance/invoices"],
        ["Payments", "/finance/payments"],
        ["Customer Balances", "/finance/customer-balances"],
        ["Supplier Balances", "/finance/supplier-balances"],
      ],
    },
    {
      label: "Administration",
      base: "/administration",
      links: [
        ["Dashboard", "/administration"],
        ["Customers", "/administration/customers"],
        ["Contacts", "/administration/contacts"],
        ["Users", "/administration/users"],
        ["Settings", "/administration/settings"],
      ],
    },
  ];

  const path = canonicalPath(window.location.pathname.replace(/\/$/, "") || "/");
  const isHome = path === "/" || path === "/home" || path === "/portal";
  const oldTopbar = document.querySelector(".topbar");
  if (oldTopbar) oldTopbar.classList.add("legacy-topbar-hidden");
  document.querySelectorAll("body > header").forEach((header) => {
    header.classList.add("legacy-topbar-hidden");
  });

  const pageTitle =
    document.querySelector("[data-page-title]")?.getAttribute("data-page-title") ||
    document.querySelector(".brand h1")?.textContent ||
    document.querySelector("h1")?.textContent ||
    document.title ||
    "CMM ERP";

  const layout = document.createElement("div");
  layout.className = "app-layout-shell";
  layout.innerHTML = `
    <header class="app-layout-header">
      <button class="app-menu-button" type="button" aria-label="Open navigation menu" aria-expanded="false">☰</button>
      <div class="app-layout-title">
        <strong>${escapeHtml(isHome ? "Home / Departments" : pageTitle)}</strong>
        <span>${escapeHtml(isHome ? "Select a department" : activeDepartmentLabel(path))}</span>
      </div>
      ${isHome ? "" : '<a class="app-home-button" href="/">Home</a>'}
    </header>
    <div class="app-menu-backdrop" hidden></div>
    <aside class="app-side-menu" aria-label="Main navigation" aria-hidden="true">
      <div class="app-side-head">
        <strong>Navigation</strong>
        <button type="button" class="app-menu-close" aria-label="Close navigation menu">×</button>
      </div>
      <a class="app-menu-home ${isHome ? "active" : ""}" href="/">Home</a>
      <nav class="app-menu-groups">
        ${departments.map(groupMarkup).join("")}
      </nav>
    </aside>
  `;
  document.body.insertBefore(layout, document.body.firstChild);
  document.body.classList.add("app-layout-active");
  if (isHome) document.body.classList.add("app-home-page");

  const menu = layout.querySelector(".app-side-menu");
  const backdrop = layout.querySelector(".app-menu-backdrop");
  const openButton = layout.querySelector(".app-menu-button");
  const closeButton = layout.querySelector(".app-menu-close");

  function setMenu(open) {
    menu.classList.toggle("open", open);
    menu.setAttribute("aria-hidden", String(!open));
    openButton.setAttribute("aria-expanded", String(open));
    backdrop.hidden = !open;
    document.body.classList.toggle("app-menu-open", open);
  }

  openButton.addEventListener("click", () => setMenu(!menu.classList.contains("open")));
  closeButton.addEventListener("click", () => setMenu(false));
  backdrop.addEventListener("click", () => setMenu(false));
  document.addEventListener("keydown", (event) => {
    if (event.key === "Escape") setMenu(false);
  });
  menu.querySelectorAll(".app-group-toggle").forEach((button) => {
    button.addEventListener("click", () => {
      const group = button.closest(".app-menu-group");
      const open = !group.classList.contains("open");
      group.classList.toggle("open", open);
      button.setAttribute("aria-expanded", String(open));
    });
  });

  function groupMarkup(group) {
    const active = isGroupActive(group, path);
    const activeHref = activeLinkHref(group, path);
    return `
      <section class="app-menu-group ${active ? "open" : ""}">
        <button class="app-group-toggle" type="button" aria-expanded="${active ? "true" : "false"}">
          <span>${escapeHtml(group.label)}</span><span aria-hidden="true">⌄</span>
        </button>
        <div class="app-group-links">
          ${group.links
            .map(([label, href]) => `<a class="${href === activeHref ? "active" : ""}" href="${href}">${escapeHtml(label)}</a>`)
            .join("")}
        </div>
      </section>
    `;
  }

  function activeDepartmentLabel(currentPath) {
    const group = departments.find((item) => isGroupActive(item, currentPath));
    return group ? group.label : "ERP";
  }

  function isGroupActive(group, currentPath) {
    const base = group.base.replace(/\/$/, "") || "/";
    return currentPath === base || currentPath.startsWith(`${base}/`);
  }

  function activeLinkHref(group, currentPath) {
    const matches = group.links
      .map(([, href]) => href.replace(/\/$/, "") || "/")
      .filter((href) => currentPath === href || currentPath.startsWith(`${href}/`))
      .sort((a, b) => b.length - a.length);
    return matches[0] || "";
  }

  function escapeHtml(value) {
    return String(value ?? "").replace(/[&<>"']/g, (char) => ({
      "&": "&amp;",
      "<": "&lt;",
      ">": "&gt;",
      '"': "&quot;",
      "'": "&#039;",
    }[char]));
  }

  function canonicalPath(value) {
    if (value === "/portal" || value === "/home") return "/";
    if (value === "/after-sales" || value.startsWith("/after-sales/")) {
      return value.replace("/after-sales", "/aftersales");
    }
    if (value === "/financials" || value.startsWith("/financials/")) {
      return value.replace("/financials", "/finance");
    }
    if (value === "/admin" || value.startsWith("/admin/")) {
      return value.replace("/admin", "/administration");
    }
    return value;
  }
})();
