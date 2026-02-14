### Aanirids Isp

Aanirids ISP

### Installation

You can install this app using the [bench](https://github.com/frappe/bench) CLI:

```bash
cd $PATH_TO_YOUR_BENCH
bench get-app $URL_OF_THIS_REPO --branch develop
bench install-app aanirids_isp
```

### Configuration

1. In Desk, open **Aanirids ISP Settings**
2. Set **Base URL** (example: `http://172.24.160.1:5003`)
3. (Optional) Set **Default ISP ID / Branch ID** for scoped sync calls
4. (Optional) Set **Default User ID / Default Username** to populate `x-user-id` / `x-username` headers for `/system-users` calls

### Contributing

This app uses `pre-commit` for code formatting and linting. Please [install pre-commit](https://pre-commit.com/#installation) and enable it for this repository:

```bash
cd apps/aanirids_isp
pre-commit install
```

Pre-commit is configured to use the following tools for checking and formatting your code:

- ruff
- eslint
- prettier
- pyupgrade

### License

mit
