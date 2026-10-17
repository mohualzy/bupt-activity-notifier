/*
 * Windows Native Messaging stdio launcher for the Python validation host.
 *
 * Edge needs a direct .exe host path, not "python.exe script.py". This small
 * Win32 GUI-subsystem launcher forwards only Edge's own inherited binary
 * stdin/stdout pipes, never touches browser profiles or network sockets.
 * Python executable path is read from per-user installer registry settings.
 */
#define WIN32_LEAN_AND_MEAN
#include <windows.h>
#include <stdio.h>
#include <string.h>
#include <wchar.h>

#define PY_REG_KEY L"Software\\mohualzy\\BUPTActivityNotifier\\EdgeSync"
#define PY_REG_VALUE L"PythonExecutable"
#define ORIGIN_PREFIX L"chrome-extension://"
#define SCRIPT_NAME L"edge_native_host.py"

static HANDLE inherit_copy(HANDLE handle) {
    HANDLE copy = NULL;
    if (handle == NULL || handle == INVALID_HANDLE_VALUE) return NULL;
    if (!DuplicateHandle(GetCurrentProcess(), handle, GetCurrentProcess(),
                         &copy, 0, TRUE, DUPLICATE_SAME_ACCESS)) return NULL;
    return copy;
}

static int valid_origin(const wchar_t *str) {
    size_t i, n;
    if (!str) return 0;
    n = wcslen(str);
    if (n != 52 || wcsncmp(str, ORIGIN_PREFIX, 19) != 0 || str[n-1] != L'/') return 0;
    for (i = 19; i < n - 1; ++i) {
        if (str[i] < L'a' || str[i] > L'p') return 0;
    }
    return 1;
}

int wmain(int argc, wchar_t **argv) {
    wchar_t python_exe[MAX_PATH] = {0};
    wchar_t path[MAX_PATH] = {0};
    wchar_t command[MAX_PATH * 3] = {0};
    DWORD bytes = sizeof(python_exe);
    DWORD chars;
    wchar_t *separator;
    STARTUPINFOW si;
    PROCESS_INFORMATION pi;
    HANDLE stdin_copy, stdout_copy, stderr_copy, null_error = NULL;
    DWORD rc = 3, child_exit = 3, wait_state;

    if (argc < 2 || !valid_origin(argv[1])) return 2;
    if (RegGetValueW(HKEY_CURRENT_USER, PY_REG_KEY, PY_REG_VALUE,
                     RRF_RT_REG_SZ, NULL, python_exe, &bytes) != ERROR_SUCCESS) return 3;
    if (GetFileAttributesW(python_exe) == INVALID_FILE_ATTRIBUTES) return 4;

    chars = GetModuleFileNameW(NULL, path, MAX_PATH);
    if (!chars || chars >= MAX_PATH - 32) return 5;
    separator = wcsrchr(path, L'\\');
    if (!separator) return 5;
    *(separator + 1) = 0;
    if (wcslen(path) + wcslen(SCRIPT_NAME) + 1 >= MAX_PATH) return 5;
    wcscat(path, SCRIPT_NAME);
    if (GetFileAttributesW(path) == INVALID_FILE_ATTRIBUTES) return 6;

    if (swprintf(command, sizeof(command) / sizeof(wchar_t),
                 L"\"%ls\" \"%ls\" \"%ls\"", python_exe, path, argv[1]) < 0) return 7;

    stdin_copy = inherit_copy(GetStdHandle(STD_INPUT_HANDLE));
    stdout_copy = inherit_copy(GetStdHandle(STD_OUTPUT_HANDLE));
    if (!stdin_copy || !stdout_copy) {
        if (stdin_copy) CloseHandle(stdin_copy);
        if (stdout_copy) CloseHandle(stdout_copy);
        return 8;
    }
    stderr_copy = inherit_copy(GetStdHandle(STD_ERROR_HANDLE));
    if (!stderr_copy) {
        null_error = CreateFileW(L"NUL", GENERIC_WRITE, FILE_SHARE_WRITE,
                                 NULL, OPEN_EXISTING, FILE_ATTRIBUTE_NORMAL, NULL);
        stderr_copy = inherit_copy(null_error);
    }

    memset(&si, 0, sizeof(si));
    memset(&pi, 0, sizeof(pi));
    si.cb = sizeof(si);
    si.dwFlags = STARTF_USESTDHANDLES;
    si.hStdInput = stdin_copy;
    si.hStdOutput = stdout_copy;
    si.hStdError = stderr_copy ? stderr_copy : stdout_copy;

    if (CreateProcessW(python_exe, command, NULL, NULL, TRUE, CREATE_NO_WINDOW,
                       NULL, NULL, &si, &pi)) {
        wait_state = WaitForSingleObject(pi.hProcess, 60000);
        if (wait_state == WAIT_TIMEOUT) TerminateProcess(pi.hProcess, 9);
        if (wait_state == WAIT_OBJECT_0 && GetExitCodeProcess(pi.hProcess, &child_exit)) {
            rc = child_exit;
        }
        CloseHandle(pi.hThread);
        CloseHandle(pi.hProcess);
    }

    CloseHandle(stdin_copy);
    CloseHandle(stdout_copy);
    if (stderr_copy) CloseHandle(stderr_copy);
    if (null_error && null_error != INVALID_HANDLE_VALUE) CloseHandle(null_error);
    return (int) rc;
}
