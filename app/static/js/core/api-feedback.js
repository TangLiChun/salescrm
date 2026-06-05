import { errorMessage } from "./utils.js";
import { notifyError, notifySuccess } from "./toast.js";

export function showApiError(error, fallback = "") {
  notifyError(errorMessage(error, fallback));
}

export function showApiSuccess(message) {
  notifySuccess(message);
}
