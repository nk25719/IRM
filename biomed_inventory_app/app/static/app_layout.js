(function () {
  if (document.documentElement.dataset.irmLayoutInitialized === "true") {
    return;
  }
  document.documentElement.dataset.irmLayoutInitialized = "true";

  const SIDEBAR_STORAGE_KEY = "irm.sidebar.collapsed";
  const desktopQuery = window.matchMedia("(min-width: 861px)");
  const savedSidebarCollapsed = readSidebarPreference();
  if (savedSidebarCollapsed && desktopQuery.matches) {
    document.body.classList.add("sidebar-collapsed");
  }

  const modules = [
    { label: "Home", href: "/", icon: "H", match: ["/", "/home", "/portal"] },
    {
      label: "Dashboard",
      href: "/dashboard",
      icon: "D",
      section: "Main Operations",
    },
    {
      label: "Sales",
      href: "/sales",
      icon: "S",
      section: "Main Operations",
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
      href: "/procurement",
      icon: "P",
      section: "Main Operations",
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
      href: "/warehouse",
      icon: "W",
      section: "Main Operations",
      match: ["/warehouse", "/inventory"],
      links: [
        ["Dashboard", "/warehouse"],
        ["Stock Items", "/warehouse/stock-items"],
        ["Receptions", "/warehouse/receptions"],
        ["Delivery Orders", "/warehouse/delivery-orders"],
        ["Minimum Stock Alerts", "/warehouse/minimum-stock"],
        ["Stock Movement", "/warehouse/stock-movement"],
        ["Warehouse Count", "/warehouse/inventory-count"],
      ],
    },
    {
      label: "Aftermarket",
      href: "/aftersales",
      icon: "A",
      section: "Main Operations",
      match: ["/aftersales", "/after-sales", "/service/contract-intelligence", "/service/customer-contracts", "/administration/manufacturer-coverage"],
      links: [
        ["Dashboard", "/aftersales/dashboard"],
        ["Service Calls", "/aftersales/service-calls"],
        ["Quotations", "/aftersales/quotations"],
        ["Preventive Maintenance", "/aftersales/preventive-maintenance"],
        ["Installations", "/aftersales/installations"],
        ["Deliveries", "/aftersales/deliveries"],
        ["Trainings", "/aftersales/trainings"],
        ["Contracts", "/aftersales/contracts"],
        ["Spare Parts Requests", "/aftersales/spare-parts"],
        ["FMI / Technical Cases", "/aftersales/technical-cases"],
      ],
    },
    {
      label: "Finance",
      href: "/finance",
      icon: "F",
      section: "Main Operations",
      match: ["/finance", "/financials"],
      links: [
        ["Dashboard", "/finance"],
        ["Invoices", "/finance/invoices"],
        ["Payments", "/finance/payments"],
        ["Customer Balances", "/finance/customer-balances"],
        ["Supplier Balances", "/finance/supplier-balances"],
      ],
    },
    {
      label: "Clients",
      href: "/clients",
      icon: "C",
      section: "Master Data / Relationship",
      match: ["/clients", "/crm", "/crm/client"],
    },
    {
      label: "Products",
      href: "/products",
      icon: "P",
      section: "Master Data / Relationship",
      match: ["/products", "/sales/products"],
    },
    {
      label: "Training & Demo",
      href: "/training-demo",
      icon: "T",
      section: "Master Data / Relationship",
      match: ["/training-demo", "/training"],
    },
    {
      label: "Administration",
      href: "/administration",
      icon: "M",
      section: "System",
      match: ["/administration", "/admin", "/departments", "/equipment", "/cases", "/imports"],
      links: [
        ["Dashboard", "/administration"],
        ["Users & Permissions", "/administration/users"],
        ["Master Data", "/administration/master-data"],
        ["Data Management", "/administration/data-management"],
        ["Backups", "/admin/database-map"],
        ["Database Map", "/admin/database-map"],
        ["Query Reports", "/admin/query"],
        ["System Settings", "/administration/settings"],
      ],
    },
    {
      label: "Reports",
      href: "/reports",
      icon: "R",
      section: "System",
    },
  ];

  const subnav = {
    "/dashboard": [
      ["By Customer", "/dashboard#customer"],
      ["Aftermarket", "/dashboard#after-sales"],
      ["Sales Pipeline", "/dashboard#sales-pipeline"],
      ["Procurement", "/dashboard#procurement"],
    ],
    "/sales": [
      ["Dashboard", "/sales"],
      ["Quotations", "/sales/quotations"],
      ["Customer Orders", "/sales/customer-orders"],
      ["Products", "/sales/products"],
      ["Reports", "/sales/reports"],
    ],
    "/procurement": [
      ["Dashboard", "/procurement"],
      ["Purchase Orders", "/procurement/purchase-orders"],
      ["Suppliers", "/procurement/suppliers"],
      ["Shipments", "/procurement/shipments"],
      ["Reports", "/procurement/reports"],
    ],
    "/warehouse": [
      ["Dashboard", "/warehouse"],
      ["Stock Items", "/warehouse/stock-items"],
      ["Receptions", "/warehouse/receptions"],
      ["Delivery Orders", "/warehouse/delivery-orders"],
      ["Minimum Stock Alerts", "/warehouse/minimum-stock"],
      ["Stock Movement", "/warehouse/stock-movement"],
      ["Warehouse Count", "/warehouse/inventory-count"],
    ],
    "/aftersales": [
      ["Dashboard", "/aftersales/dashboard"],
      ["Service Calls", "/aftersales/service-calls"],
      ["Quotations", "/aftersales/quotations"],
      ["Preventive Maintenance", "/aftersales/preventive-maintenance"],
      ["Installations", "/aftersales/installations"],
      ["Deliveries", "/aftersales/deliveries"],
      ["Trainings", "/aftersales/trainings"],
      ["Contracts", "/aftersales/contracts"],
      ["Spare Parts Requests", "/aftersales/spare-parts"],
      ["FMI / Technical Cases", "/aftersales/technical-cases"],
    ],
    "/finance": [
      ["Dashboard", "/finance"],
      ["Invoices", "/finance/invoices"],
      ["Payments", "/finance/payments"],
      ["Customer Balances", "/finance/customer-balances"],
      ["Supplier Balances", "/finance/supplier-balances"],
    ],
    "/administration": [
      ["Dashboard", "/administration"],
      ["Users & Permissions", "/administration/users"],
      ["Master Data", "/administration/master-data"],
      ["Data Management", "/administration/data-management"],
      ["Backups", "/admin/database-map"],
      ["Database Map", "/admin/database-map"],
      ["Query Reports", "/admin/query"],
      ["System Settings", "/administration/settings"],
    ],
  };

  const dataActions = [
    {
      match: ["/warehouse", "/warehouse/stock-items", "/warehouse/stock-movement", "/warehouse/inventory-count"],
      title: "Warehouse Data",
      importHref: "/administration/data-management#import",
      importLabel: "Import Stock",
      exportHref: "/api/export",
      exportLabel: "Full ERP Export",
      manageHref: "/administration/data-management?dataset=warehouse_stock",
    },
    {
      match: ["/crm/contacts"],
      title: "Contact Data",
      importHref: "#contact-import",
      importLabel: "Import Contacts",
      exportHref: "/api/contacts/export",
      exportLabel: "Export Contacts",
      manageHref: "/administration/data-management?dataset=contacts",
    },
    {
      match: ["/clients", "/crm"],
      title: "Client Data",
      importHref: "/administration/data-management?dataset=clients#import",
      importLabel: "Import Clients",
      exportHref: "/administration/data-management?dataset=clients#export",
      exportLabel: "Export Clients",
      manageHref: "/administration/data-management",
    },
    {
      match: ["/equipment", "/aftersales/installed-base"],
      title: "Equipment Data",
      importHref: "/administration/data-management?dataset=equipment#import",
      importLabel: "Import Equipment",
      exportHref: "/api/exports/equipment-database",
      exportLabel: "Export Equipment",
      manageHref: "/administration/data-management?dataset=equipment",
    },
    {
      match: ["/sales/quotations", "/aftersales/quotations"],
      title: "Quotation Data",
      importHref: "#quotation-import",
      importLabel: "Import Quotation",
      exportHref: "#quotation-export",
      exportLabel: "Export Selected",
      manageHref: "/administration/data-management?dataset=quotations",
    },
    {
      match: ["/aftersales/schedule"],
      title: "Schedule Data",
      importHref: "#schedule-import",
      importLabel: "Import Schedule",
      exportHref: "/api/schedule/export",
      exportLabel: "Export Schedule",
      extra: [["Weekly Grid", "/api/schedule/export?grid=true"]],
    },
    {
      match: ["/service/contract-intelligence", "/aftersales/contract-intelligence"],
      title: "Contract Intelligence Data",
      importHref: "/administration/data-management#import",
      importLabel: "Import Coverage",
      exportHref: "/api/service-intelligence/export",
      exportLabel: "Export Opportunities",
      manageHref: "/administration/data-management",
    },
    {
      match: ["/procurement"],
      title: "Procurement Data",
      importHref: "/administration/data-management?dataset=purchase_orders#import",
      importLabel: "Import Procurement",
      exportHref: "/api/exports/procurement",
      exportLabel: "Export Procurement",
      manageHref: "/administration/data-management",
    },
    {
      match: ["/sales"],
      title: "Sales Data",
      importHref: "/administration/data-management?dataset=sales#import",
      importLabel: "Import Sales",
      exportHref: "/api/exports/sales_requests",
      exportLabel: "Export Sales",
      manageHref: "/administration/data-management",
    },
    {
      match: ["/administration/data-management"],
      title: "Data Management",
      importHref: "#import",
      importLabel: "Import",
      exportHref: "#export",
      exportLabel: "Export",
      extra: [["Templates", "#templates"], ["History", "#history"]],
    },
  ];

  const rawPath = window.location.pathname.replace(/\/$/, "") || "/";
  const path = canonicalPath(rawPath);
  const isHome = path === "/";
  const activeModule = findActiveModule(path);
  const pageTitle = getPageTitle(isHome, activeModule);
  const breadcrumb = getBreadcrumb(isHome, activeModule, path);
  const backTarget = getBackTarget(path, activeModule);
  const showBack = Boolean(backTarget);

  hideLegacyChrome();

  const shell = document.createElement("div");
  shell.className = "erp-shell app-shell";
  shell.innerHTML = `
    <aside class="erp-sidebar app-sidebar" data-app-sidebar aria-label="Primary navigation">
      <a class="erp-brand" href="/">
        <span class="erp-brand-mark">IR</span>
        <span class="erp-brand-text"><strong>IRM ERM</strong><small>Operations Suite</small></span>
      </a>
      <button class="erp-sidebar-collapse app-sidebar__toggle" type="button" aria-label="Collapse sidebar" aria-expanded="true">
        <span aria-hidden="true">‹</span>
      </button>
      <nav class="erp-nav" aria-label="Departments">
        ${renderNavigation()}
      </nav>
    </aside>
    <div class="erp-mobile-backdrop" hidden></div>
    <header class="erp-topbar app-header">
      <button class="erp-menu-toggle" type="button" aria-label="Open navigation" aria-expanded="false">☰</button>
      ${showBack ? `<button class="erp-back-button" type="button" data-back-target="${escapeHtml(backTarget)}">← Back</button>` : ""}
      <div class="erp-title-block">
        <div class="erp-breadcrumb">${escapeHtml(breadcrumb)}</div>
        <h1>${escapeHtml(pageTitle)}</h1>
      </div>
      <label class="erp-search" aria-label="Search">
        <span>⌕</span>
        <input type="search" placeholder="Search clients, CO#, PO#, stock..." />
      </label>
      <a class="erp-user" href="/logout" title="Logout" aria-label="Current user logout">
        <span>NK</span>
      </a>
    </header>
  `;
  document.body.insertBefore(shell, document.body.firstChild);
  document.body.classList.add("erp-layout-active");
  if (isHome) document.body.classList.add("erp-home-page");

  const menuButton = shell.querySelector(".erp-menu-toggle");
  const collapseButton = shell.querySelector(".erp-sidebar-collapse");
  const sidebar = shell.querySelector(".erp-sidebar");
  const backdrop = shell.querySelector(".erp-mobile-backdrop");
  const backButton = shell.querySelector(".erp-back-button");
  syncCollapseButton();
  shell.querySelectorAll(".erp-nav-toggle").forEach((button) => {
    button.addEventListener("click", () => {
      const group = button.closest(".erp-nav-group");
      const isOpen = group.classList.toggle("open");
      button.setAttribute("aria-expanded", String(isOpen));
    });
  });
  menuButton.addEventListener("click", () => setSidebar(!sidebar.classList.contains("open")));
  collapseButton.addEventListener("click", () => {
    const collapsed = !document.body.classList.contains("sidebar-collapsed");
    document.body.classList.toggle("sidebar-collapsed", collapsed);
    localStorage.setItem(SIDEBAR_STORAGE_KEY, collapsed ? "true" : "false");
    syncCollapseButton();
  });
  desktopQuery.addEventListener?.("change", () => {
    document.body.classList.toggle("sidebar-collapsed", readSidebarPreference() && desktopQuery.matches);
    syncCollapseButton();
  });
  backdrop.addEventListener("click", () => setSidebar(false));
  if (backButton) {
    backButton.addEventListener("click", () => {
      const target = backButton.getAttribute("data-back-target") || "/";
      if (window.history.length > 1 && document.referrer && sameOrigin(document.referrer)) {
        window.history.back();
        return;
      }
      window.location.href = target;
    });
  }
  document.addEventListener("keydown", (event) => {
    if (event.key === "Escape") setSidebar(false);
  });

  addSubnav(activeModule, path);
  addDataActions(path);

  function addSubnav(module, currentPath) {
    const links = subnav[module.href];
    if (!links || isHome) return;
    const main = document.querySelector("main");
    if (!main || main.querySelector("[data-section-tabs], .erp-page-tabs")) return;
    const activeHref = activeSubnavHref(links, currentPath);
    const tabs = document.createElement("nav");
    tabs.className = "erp-page-tabs section-tabs department-nav";
    tabs.dataset.sectionTabs = slugify(module.label);
    tabs.dataset.departmentNav = slugify(module.label);
    tabs.setAttribute("aria-label", `${module.label} sections`);
    tabs.innerHTML = links
      .map(([label, href]) => `<a class="section-tab department-nav__item ${href === activeHref ? "active" : ""}" ${href === activeHref ? 'aria-current="page"' : ""} href="${href}">${escapeHtml(label)}</a>`)
      .join("");
    main.insertBefore(tabs, main.firstElementChild);
  }

  function addDataActions(currentPath) {
    const main = document.querySelector("main");
    if (!main || isHome || main.querySelector("[data-irm-data-actions]")) return;
    const config = dataActions.find((item) => item.match.some((value) => {
      const normalized = canonicalPath(value.replace(/\/$/, "") || "/");
      return currentPath === normalized || (normalized !== "/" && currentPath.startsWith(`${normalized}/`));
    }));
    if (!config) return;
    const actions = [
      [config.importLabel, config.importHref, "import"],
      [config.exportLabel, config.exportHref, "export"],
      ...(config.extra || []).map(([label, href]) => [label, href, "extra"]),
      ...(config.manageHref ? [["Data Center", config.manageHref, "manage"]] : []),
    ];
    const strip = document.createElement("section");
    strip.className = "irm-data-actions";
    strip.dataset.irmDataActions = slugify(config.title);
    strip.setAttribute("aria-label", `${config.title} import and export actions`);
    strip.innerHTML = `
      <div>
        <strong>${escapeHtml(config.title)}</strong>
        <span>Import, export, and review the records behind this view.</span>
      </div>
      <div class="irm-data-actions__buttons">
        ${actions.map(([label, href, kind]) => `<a class="irm-data-action irm-data-action--${kind}" href="${escapeHtml(href)}">${escapeHtml(label)}</a>`).join("")}
      </div>
    `;
    const firstSectionTabs = main.querySelector("[data-section-tabs], .erp-page-tabs");
    if (firstSectionTabs?.nextSibling) {
      main.insertBefore(strip, firstSectionTabs.nextSibling);
      return;
    }
    main.insertBefore(strip, main.firstElementChild);
  }

  function syncCollapseButton() {
    const collapsed = document.body.classList.contains("sidebar-collapsed") && desktopQuery.matches;
    collapseButton.setAttribute("aria-label", collapsed ? "Expand sidebar" : "Collapse sidebar");
    collapseButton.setAttribute("aria-expanded", String(!collapsed));
    collapseButton.querySelector("span").textContent = collapsed ? "›" : "‹";
  }

  function setSidebar(open) {
    sidebar.classList.toggle("open", open);
    menuButton.setAttribute("aria-expanded", String(open));
    backdrop.hidden = !open;
    document.body.classList.toggle("erp-menu-open", open);
  }

  function navItem(module, active, currentPath) {
    const moduleKey = escapeHtml(slugify(module.label));
    if (!module.links) {
      return `
        <a class="erp-nav-item app-sidebar__item ${active ? "active" : ""}" ${active ? 'aria-current="page"' : ""} href="${module.href}" data-module="${moduleKey}" title="${escapeHtml(module.label)}">
          <span>${escapeHtml(module.icon)}</span>
          <strong class="erp-nav-label app-sidebar__label">${escapeHtml(module.label)}</strong>
        </a>
      `;
    }
    const activeHref = activeSubnavHref(module.links, currentPath);
    const expanded = active || module.href === "/sales" || module.href === "/aftersales";
    return `
      <section class="erp-nav-group ${expanded ? "open" : ""}" data-module="${moduleKey}">
        <button class="erp-nav-item app-sidebar__item erp-nav-toggle ${active ? "active" : ""}" type="button" aria-expanded="${expanded}" title="${escapeHtml(module.label)}">
          <span>${escapeHtml(module.icon)}</span>
          <strong class="erp-nav-label app-sidebar__label">${escapeHtml(module.label)}</strong>
          <i aria-hidden="true">▾</i>
        </button>
        <div class="erp-nav-children">
          ${module.links.map(([label, href]) => `
            <a class="${href === activeHref ? "active" : ""}" ${href === activeHref ? 'aria-current="page"' : ""} href="${href}">${escapeHtml(label)}</a>
          `).join("")}
        </div>
      </section>
    `;
  }

  function isActive(module, currentPath) {
    const matches = module.match || [module.href];
    return matches.some((value) => {
      const normalized = canonicalPath(value.replace(/\/$/, "") || "/");
      return currentPath === normalized || (normalized !== "/" && currentPath.startsWith(`${normalized}/`));
    });
  }

  function findActiveModule(currentPath) {
    return modules
      .map((module) => ({ module, score: activeScore(module, currentPath) }))
      .filter((item) => item.score >= 0)
      .sort((a, b) => b.score - a.score)[0]?.module || modules[0];
  }

  function activeScore(module, currentPath) {
    const matches = module.match || [module.href];
    return matches.reduce((best, value) => {
      const normalized = canonicalPath(value.replace(/\/$/, "") || "/");
      const matched = currentPath === normalized || (normalized !== "/" && currentPath.startsWith(`${normalized}/`));
      return matched ? Math.max(best, normalized.length) : best;
    }, -1);
  }

  function activeSubnavHref(links, currentPath) {
    const currentHash = window.location.hash || "";
    if (currentHash) {
      const hashMatch = links.find(([, href]) => {
        const [hrefPath, hrefHash = ""] = href.split("#");
        const base = canonicalPath(hrefPath.replace(/\/$/, "") || "/");
        return base === currentPath && `#${hrefHash}` === currentHash;
      });
      if (hashMatch) return hashMatch[1];
    }
    const aftermarketParent = aftermarketParentHref(currentPath);
    if (aftermarketParent && links.some(([, href]) => href === aftermarketParent)) return aftermarketParent;
    return links
      .map(([, href]) => href)
      .filter((href) => {
        const base = canonicalPath(href.split("#")[0].replace(/\/$/, "") || "/");
        return currentPath === base || (base !== "/" && currentPath.startsWith(`${base}/`));
      })
      .sort((a, b) => b.split("#")[0].length - a.split("#")[0].length)[0] || "";
  }

  function aftermarketParentHref(currentPath) {
    if (!currentPath.startsWith("/aftersales/")) return "";
    if (currentPath === "/aftersales/dashboard") return "/aftersales/dashboard";
    if (
      currentPath.includes("/service-calls") ||
      currentPath.includes("/service-cases") ||
      currentPath.includes("/service-history") ||
      currentPath.includes("/installed-base") ||
      currentPath.startsWith("/aftersales/equipment")
    ) return "/aftersales/service-calls";
    if (currentPath.includes("/quotations")) return "/aftersales/quotations";
    if (currentPath.includes("/preventive-maintenance") || currentPath.includes("/pm") || currentPath.includes("/pm-tracking") || currentPath.includes("/schedule")) return "/aftersales/preventive-maintenance";
    if (currentPath.includes("/installations") || currentPath.includes("/delivery-installation")) return "/aftersales/installations";
    if (currentPath.includes("/deliveries")) return "/aftersales/deliveries";
    if (currentPath.includes("/trainings") || currentPath.includes("/training-demo")) return "/aftersales/trainings";
    if (currentPath.includes("/contracts") || currentPath.includes("/contract-intelligence") || currentPath.includes("/customer-contracts") || currentPath.includes("/coverage") || currentPath.endsWith("/warranty")) return "/aftersales/contracts";
    if (currentPath.includes("/spare-parts")) return "/aftersales/spare-parts";
    if (currentPath.includes("/technical-cases") || currentPath.includes("/fmi-recall") || currentPath.includes("/fmi-field-modifications") || currentPath.includes("/analytics")) return "/aftersales/technical-cases";
    return "/aftersales/dashboard";
  }

  function getBackTarget(currentPath, module) {
    const mainPages = new Set([
      "/",
      "/dashboard",
      "/sales",
      "/procurement",
      "/warehouse",
      "/aftersales",
      "/finance",
      "/clients",
      "/products",
      "/training-demo",
      "/administration",
      "/reports",
    ]);
    if (mainPages.has(currentPath)) return "";
    if (currentPath.startsWith("/crm/client/")) return "/clients";
    if (currentPath === "/departments" || currentPath === "/equipment" || currentPath === "/cases" || currentPath === "/imports") return "/administration";
    if (currentPath.startsWith("/sales/quotations")) return "/sales";
    if (currentPath.startsWith("/sales/customer-orders")) return "/sales";
    if (currentPath.startsWith("/sales/products")) return "/products";
    if (currentPath.startsWith("/procurement/")) return "/procurement";
    if (currentPath.startsWith("/warehouse/")) return "/warehouse";
    if (currentPath.startsWith("/aftersales/")) return "/aftersales";
    if (currentPath.startsWith("/finance/")) return "/finance";
    if (currentPath.startsWith("/administration/")) return "/administration";
    if (currentPath.startsWith("/equipment")) return "/clients";
    if (currentPath.startsWith("/imports")) return "/dashboard";
    return module.href === currentPath ? "" : module.href;
  }

  function renderNavigation() {
    let currentSection = "";
    return modules.map((module) => {
      const section = module.section || "";
      const heading = section && section !== currentSection
        ? `<div class="erp-nav-section">${escapeHtml(section)}</div>`
        : "";
      if (section) currentSection = section;
      return heading + navItem(module, module === activeModule, path);
    }).join("");
  }

  function sameOrigin(url) {
    try {
      return new URL(url).origin === window.location.origin;
    } catch {
      return false;
    }
  }

  function getPageTitle(home, module) {
    if (home) return "Home";
    return (
      document.body.getAttribute("data-page-title") ||
      document.querySelector("[data-page-title]")?.getAttribute("data-page-title") ||
      document.querySelector(".brand h1")?.textContent ||
      document.querySelector("h1")?.textContent ||
      document.title ||
      module.label
    ).replace(/\bInventory\b/g, "Warehouse");
  }

  function getBreadcrumb(home, module, currentPath) {
    if (home) return "ERM / Home";
    const activeSection = activeSubnavHref(module.links, currentPath);
    const sectionLabel = module.links?.find(([, href]) => href === activeSection)?.[0];
    return sectionLabel ? `ERM / ${module.label} / ${sectionLabel}` : `ERM / ${module.label}`;
  }

  function hideLegacyChrome() {
    document.querySelectorAll(".topbar, body > header, .burger, .drawer, .drawer-backdrop, .pm-burger, .pm-sidebar").forEach((node) => {
      node.classList.add("legacy-topbar-hidden");
    });
  }

  function canonicalPath(value) {
    if (value === "/portal" || value === "/home") return "/";
    if (value === "/after-sales" || value.startsWith("/after-sales/")) return value.replace("/after-sales", "/aftersales");
    if (value === "/service/contract-intelligence" || value.startsWith("/service/contract-intelligence/")) return value.replace("/service/contract-intelligence", "/aftersales/contract-intelligence");
    if (value === "/service/customer-contracts" || value.startsWith("/service/customer-contracts/")) return value.replace("/service/customer-contracts", "/service/contract-intelligence/customer-contracts");
    if (value === "/administration/manufacturer-coverage" || value.startsWith("/administration/manufacturer-coverage/")) return value.replace("/administration/manufacturer-coverage", "/service/contract-intelligence/manufacturer-coverage");
    if (value === "/financials" || value.startsWith("/financials/")) return value.replace("/financials", "/finance");
    if (value === "/admin" || value.startsWith("/admin/")) return value.replace("/admin", "/administration");
    if (value === "/inventory" || value.startsWith("/inventory/")) return value.replace("/inventory", "/warehouse");
    if (value === "/training" || value.startsWith("/training/")) return value.replace("/training", "/training-demo");
    return value;
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

  function readSidebarPreference() {
    try {
      return localStorage.getItem(SIDEBAR_STORAGE_KEY) === "true";
    } catch {
      return false;
    }
  }

  function slugify(value) {
    return String(value ?? "")
      .toLowerCase()
      .replace(/&/g, "and")
      .replace(/[^a-z0-9]+/g, "-")
      .replace(/^-|-$/g, "");
  }
})();
