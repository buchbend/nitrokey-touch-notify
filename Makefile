PREFIX      ?= $(HOME)/.local
BINDIR       = $(PREFIX)/bin
SYSTEMD_DIR  = $(HOME)/.config/systemd/user
SHELL_HOOK   = $(HOME)/.config/nitrokey-touch-notify/shell-integration.sh

.PHONY: install uninstall enable disable status restart log

install: ## Install binary, systemd service, and shell integration
	install -Dm755 nitrokey_touch_notify.py $(BINDIR)/nitrokey-touch-notify
	install -Dm644 nitrokey-touch-notify.service $(SYSTEMD_DIR)/nitrokey-touch-notify.service
	sed -i 's|%h/git/nitrokey-touch-notify/nitrokey_touch_notify.py|$(BINDIR)/nitrokey-touch-notify|' \
		$(SYSTEMD_DIR)/nitrokey-touch-notify.service
	install -Dm644 shell-integration.sh $(SHELL_HOOK)
	systemctl --user daemon-reload
	@echo ""
	@echo "Installed. Next steps:"
	@echo "  make enable                    # enable and start the service"
	@echo "  Add to ~/.bashrc:"
	@echo "    source $(SHELL_HOOK)"

uninstall: disable ## Remove everything
	rm -f $(BINDIR)/nitrokey-touch-notify
	rm -f $(SYSTEMD_DIR)/nitrokey-touch-notify.service
	rm -f $(SHELL_HOOK)
	systemctl --user daemon-reload
	@echo "Uninstalled. Remove the 'source' line from your ~/.bashrc."

enable: ## Enable and start the service
	systemctl --user enable --now nitrokey-touch-notify.service
	@echo "Service enabled and started."

disable: ## Stop and disable the service
	-systemctl --user disable --now nitrokey-touch-notify.service

status: ## Show service status
	systemctl --user status nitrokey-touch-notify.service

restart: ## Restart the service
	systemctl --user restart nitrokey-touch-notify.service

log: ## Follow service logs
	journalctl --user -u nitrokey-touch-notify -f

help: ## Show this help
	@grep -E '^[a-zA-Z_-]+:.*##' $(MAKEFILE_LIST) | awk -F ':.*## ' '{printf "  %-15s %s\n", $$1, $$2}'
