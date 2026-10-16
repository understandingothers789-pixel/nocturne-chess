/* MIT. Thin CPython binding: all native initialization/probing is serialized.
 * No chess rules or search are delegated to Fathom. */
#define PY_SSIZE_T_CLEAN
#include <Python.h>
#include <stdlib.h>
#include <string.h>
#include "tbprobe.h"

static PyThread_type_lock probe_lock;

static PyObject *probe(PyObject *self, PyObject *args) {
    const char *path;
    unsigned long long white, black, kings, queens, rooks, bishops, knights, pawns;
    unsigned rule50, ep;
    int turn, ok = 1;
    unsigned largest = 0, wdl = TB_RESULT_FAILED, result = TB_RESULT_FAILED;
    if (!PyArg_ParseTuple(args, "sKKKKKKKKIIp", &path, &white, &black, &kings,
                          &queens, &rooks, &bishops, &knights, &pawns, &rule50, &ep, &turn))
        return NULL;
    Py_BEGIN_ALLOW_THREADS
    PyThread_acquire_lock(probe_lock, WAIT_LOCK);
    /* Root probes refresh the directory so newly added tables are discovered. */
    tb_free();
    ok = tb_init(path);
    largest = TB_LARGEST;
    if (ok && largest) {
        result = tb_probe_root(white, black, kings, queens, rooks, bishops,
                               knights, pawns, rule50, 0, ep, turn, NULL);
        if (result != TB_RESULT_FAILED) wdl = TB_GET_WDL(result);
        else wdl = tb_probe_wdl(white, black, kings, queens, rooks, bishops,
                                knights, pawns, 0, 0, ep, turn);
    }
    PyThread_release_lock(probe_lock);
    Py_END_ALLOW_THREADS
    if (!ok) return PyErr_Format(PyExc_RuntimeError, "Cannot initialize Syzygy tables");
    return Py_BuildValue("(III)", largest, wdl, result);
}

static void cleanup(void *module) {
    tb_free();
    if (probe_lock) PyThread_free_lock(probe_lock);
}
static PyMethodDef methods[] = {
    {"probe", probe, METH_VARARGS, "Probe local Syzygy WDL/DTZ tables."},
    {NULL, NULL, 0, NULL}
};
static struct PyModuleDef module = {
    PyModuleDef_HEAD_INIT, "_syzygy", NULL, -1, methods, NULL, NULL, NULL, cleanup
};
PyMODINIT_FUNC PyInit__syzygy(void) {
    probe_lock = PyThread_allocate_lock();
    if (!probe_lock) return PyErr_NoMemory();
    return PyModule_Create(&module);
}
