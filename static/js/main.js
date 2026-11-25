/**
 * EnerTrack Main Interactive Utilities
 * Handles modal lifecycle, sidebar toggle for responsive mobile views, and toast notifications.
 */

document.addEventListener("DOMContentLoaded", function () {
  // 1. Mobile Sidebar Toggle
  const sidebar = document.querySelector(".sidebar");
  const sidebarToggleBtn = document.getElementById("sidebarToggle");
  if (sidebarToggleBtn && sidebar) {
    sidebarToggleBtn.addEventListener("click", function () {
      sidebar.classList.toggle("open");
    });
  }

  // 2. Alert Dismissal
  const alertCloseBtns = document.querySelectorAll(".alert-close");
  alertCloseBtns.forEach(btn => {
    btn.addEventListener("click", function () {
      const alert = this.closest(".alert");
      if (alert) {
        alert.style.opacity = "0";
        setTimeout(() => alert.remove(), 200);
      }
    });
  });

  // 3. Modal Opening and Closing (Generic)
  window.openModal = function (modalId) {
    const modal = document.getElementById(modalId);
    if (modal) {
      modal.classList.add("show");
      document.body.style.overflow = "hidden";
    }
  };

  window.closeModal = function (modalId) {
    const modal = document.getElementById(modalId);
    if (modal) {
      modal.classList.remove("show");
      document.body.style.overflow = "";
    }
  };

  // Close modals when clicking backdrop
  document.querySelectorAll(".modal-backdrop").forEach(backdrop => {
    backdrop.addEventListener("click", function (e) {
      if (e.target === this) {
        this.classList.remove("show");
        document.body.style.overflow = "";
      }
    });
  });

  // Close modal on Escape key
  document.addEventListener("keydown", function (e) {
    if (e.key === "Escape") {
      document.querySelectorAll(".modal-backdrop.show").forEach(modal => {
        modal.classList.remove("show");
      });
      document.body.style.overflow = "";
    }
  });
});
