"""Run a function from a file inside a Frappe site context:  frappe_run.py SITE FILE FUNC"""
import importlib.util
import sys

import frappe

site, path, func = sys.argv[1:4]
import os
os.chdir("/home/frappe/frappe-bench/sites")  # bench runs from the sites dir
frappe.init(site, sites_path=".")
frappe.connect()
spec = importlib.util.spec_from_file_location("_run_mod", path)
mod = importlib.util.module_from_spec(spec)
spec.loader.exec_module(mod)
getattr(mod, func)()
frappe.db.commit()
frappe.destroy()
