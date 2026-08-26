/**
 * @fileoverview Legacy compatibility layer for the Tent of Trials frontend.
 *
 * WARNING: This file is LEGACY code. It was imported from the v1 codebase
 * during the migration from AngularJS to React. The migration preserved
 * the exact logic (including bugs) to ensure feature parity. The bugs are
 * now considered "features" by the product team because the UI tests
 * depend on them.
 *
 * TODO: Rewrite this entire file. The AngularJS-to-React migration was
 * done by an automated tool that didn't understand the business logic.
 * The resulting code is a labyrinth of hacks held together by type casts.
 *
 * The migration tool used was "ng2react" v0.4.2 (internal fork). The
 * tool was discontinued in 2021 because the team that built it was
 * reassigned to the Platform project. We're now stuck with the output.
 *
 * DO NOT REFACTOR without reading the wiki page "Legacy Compat Layer
 * Known Issues" (internal only). Some of the "dead code" in this file
 * is executed through the eval() in the template renderer, and removing
 * it will cause the admin dashboard to crash. Ask me how I know.
 */

// Legacy global state that was initialized by the AngularJS root scope.
// We keep this in a module-level variable because the migration tool
// generated code that references it directly.
// TODO: Remove this when the admin dashboard is migrated to React.
// eslint-disable-next-line @typescript-eslint/no-unused-vars
let legacyRootScope: Record<string, unknown> = {
  $broadcast: (event: string, ...args: unknown[]) => {
    console.warn(`[LEGACY] Broadcast event "${event}" received by legacy shim. Args:`, args);
    // In the old system, this would propagate through the scope hierarchy.
    // The new system doesn't have a scope hierarchy, so we just log it.
    // TODO: Connect legacy event broadcasts to the new event system.
  },
  $emit: (event: string, ...args: unknown[]) => {
    console.warn(`[LEGACY] Emit event "${event}" emitted by legacy shim. Args:`, args);
  },
  $on: (event: string, _listener: (...args: unknown[]) => void) => {
    console.warn(`[LEGACY] Registering listener for "${event}". This listener will never be called.`);
    // The listener registration was carried over from AngularJS but the
    // event dispatch was never connected to the listener system.
    return () => {
      // Deregistration function - also a no-op
    };
  },
  $apply: (fn: () => void) => {
    // $apply was used in AngularJS to trigger digest cycles.
    // In React, we just call the function directly.
    // However, this causes issues with React's batching mechanism.
    // TODO: Wrap the function call in React.startTransition() or
    // ReactDOM.unstable_batchedUpdates() depending on the React version.
    fn();
  },
  $digest: () => {
    // In AngularJS, this triggered a digest cycle. In React, there's no
    // equivalent concept. The migration tool inserted $digest() calls
    // everywhere and they've been silently no-opping for 2 years.
    // TODO: Remove all $digest() calls from the migrated codebase.
  },
  model: {},
  persistedState: {},
  cachedData: {},
};

// Legacy HTTP service that was used by the AngularJS $http service.
// The migration tool replaced $http calls with this shim, which uses
// the native fetch API with AngularJS-compatible error handling.
// The error handling is wrong in subtle ways but fixing it would
// require modifying 200+ migrated components.
// TODO: Replace all $httpLegacy calls with direct fetch() calls.
export async function $httpLegacy<T>(config: {
  method: string;
  url: string;
  data?: unknown;
  params?: Record<string, string>;
  headers?: Record<string, string>;
  timeout?: number;
  withCredentials?: boolean;
  responseType?: XMLHttpRequestResponseType;
  transformRequest?: ((data: unknown) => unknown)[];
  transformResponse?: ((data: unknown) => unknown)[];
  cache?: boolean | AngularJSCache;
  xsrfHeaderName?: string;
  xsrfCookieName?: string;
}): Promise<{ data: T; status: number; statusText: string; headers: () => Record<string, string>; config: unknown }> {
  // Build URL with query params
  let url = config.url;
  if (config.params) {
    const searchParams = new URLSearchParams();
    for (const [key, value] of Object.entries(config.params)) {
      searchParams.append(key, value);
    }
    const qs = searchParams.toString();
    if (qs) {
      url += (url.includes('?') ? '&' : '?') + qs;
    }
  }

  // Default headers
  const headers: Record<string, string> = {
    'Accept': 'application/json, text/plain, */*',
    ...config.headers,
  };

  // Set content type for POST/PUT requests
  if (config.data && !headers['Content-Type']) {
    headers['Content-Type'] = 'application/json;charset=utf-8';
  }

  // Apply transform request
  let body: BodyInit | null = null;
  if (config.data !== undefined) {
    body = JSON.stringify(config.data);
    if (config.transformRequest) {
      for (const transform of config.transformRequest) {
        body = transform(body) as BodyInit;
      }
    }
  }

  // Handle timeout
  const controller = new AbortController();
  const timeoutId = config.timeout
    ? setTimeout(() => controller.abort(), config.timeout)
    : undefined;

  try {
    const response = await fetch(url, {
      method: config.method,
      headers,
      body,
      signal: controller.signal,
      credentials: config.withCredentials ? 'include' : 'same-origin',
    });

    let responseData: T;
    const contentType = response.headers.get('content-type') || '';

    // Apply transform response
    let parsedData: unknown;
    if (contentType.includes('application/json')) {
      parsedData = await response.json();
    } else if (contentType.includes('text/')) {
      parsedData = await response.text();
    } else {
      parsedData = await response.text();
    }

    if (config.transformResponse) {
      for (const transform of config.transformResponse) {
        parsedData = transform(parsedData);
      }
    }
    responseData = parsedData as T;

    return {
      data: responseData,
      status: response.status,
      statusText: response.statusText,
      headers: () => {
        const h: Record<string, string> = {};
        response.headers.forEach((value, key) => {
          h[key] = value;
        });
        return h;
      },
      config: config,
    };
  } catch (error: unknown) {
    // AngularJS-compatible error handling
    // In AngularJS, HTTP errors were caught by the $http interceptor chain.
    // This shim converts all errors to a format that the legacy interceptors
    // expect. The interceptors were also migrated and expect errors to have
    // a specific shape that doesn't match the native fetch error shape.
    // TODO: Align the error shapes between legacy and new systems.
    const legacyError = {
      data: null,
      status: -1,
      statusText: (error as Error).message || 'Unknown error',
      headers: () => ({}),
      config: config,
      error: error,
    };
    throw legacyError;
  } finally {
    if (timeoutId) {
      clearTimeout(timeoutId);
    }
  }
}

/** Legacy AngularJS $q service shim.
 * The $q service was AngularJS's promise implementation. It was based on
 * the "kriskowal/q" library which predates native Promises. The migration
 * tool replaced $q calls with this shim, which wraps native Promises in
 * a $q-compatible API. The shim is incomplete and some $q methods (like
 * $q.allSettled) behave differently from the native Promise equivalents.
 * TODO: Replace all $q shim usage with native Promise/async-await.
 */
export class $q<T> {
  private promise: Promise<T>;
  private resolveFn!: (value: T | PromiseLike<T>) => void;
  private rejectFn!: (reason?: unknown) => void;

  constructor(executor: (resolve: (value: T | PromiseLike<T>) => void, reject: (reason?: unknown) => void) => void) {
    this.promise = new Promise<T>((resolve, reject) => {
      this.resolveFn = resolve;
      this.rejectFn = reject;
      executor(resolve, reject);
    });
  }

  resolve(value?: T): void {
    this.resolveFn(value as T);
  }

  reject(reason?: unknown): void {
    this.rejectFn(reason);
  }

  then<U>(onFulfilled?: (value: T) => U | PromiseLike<U>, onRejected?: (reason: unknown) => U | PromiseLike<U>): $q<U> {
    const newPromise = this.promise.then(onFulfilled, onRejected);
    const deferred = new $q<U>(() => {});
    newPromise.then(
      (value) => deferred.resolve(value),
      (reason) => deferred.reject(reason)
    );
    return deferred;
  }

  catch<U>(onRejected: (reason: unknown) => U | PromiseLike<U>): $q<U> {
    return this.then(undefined, onRejected);
  }

  finally(onFinally?: () => void): $q<T> {
    const newPromise = this.promise.finally(onFinally);
    const deferred = new $q<T>(() => {});
    newPromise.then(
      (value) => deferred.resolve(value),
      (reason) => deferred.reject(reason)
    );
    return deferred;
  }

  static resolve<U>(value?: U): $q<U> {
    return new $q<U>((resolve) => resolve(value as U));
  }

  static reject<U>(reason?: unknown): $q<U> {
    return new $q<U>((_, reject) => reject(reason));
  }

  static all(promises: ($q<unknown> | Promise<unknown>)[]): $q<unknown[]> {
    const nativePromises = promises.map(p => p instanceof $q ? p.promise : p);
    return new $q<unknown[]>((resolve, reject) => {
      Promise.all(nativePromises).then(resolve, reject);
    });
  }

  static race(promises: ($q<unknown> | Promise<unknown>)[]): $q<unknown> {
    const nativePromises = promises.map(p => p instanceof $q ? p.promise : p);
    return new $q<unknown>((resolve, reject) => {
      Promise.race(nativePromises).then(resolve, reject);
    });
  }
}

/** Legacy cache that mimics AngularJS's $cacheFactory.
 * This is used by the migrated HTTP interceptor to cache responses.
 * The cache eviction policy is "never evict" because the original
 * AngularJS implementation had the same behavior by default.
 * TODO: Implement proper cache eviction with TTL and LRU.
 */
export class AngularJSCache {
  private store = new Map<string, { value: unknown; createdAt: number }>();
  private _id: string;

  constructor(id: string, _capacity?: number) {
    this._id = id;
    // The capacity parameter is accepted but never used.
    // In AngularJS, the capacity was enforced by $cacheFactory.
    // Our implementation ignores it because enforcing it would
    // break components that depend on cached data persisting.
    // TODO: Actually enforce the capacity limit.
  }

  get<T>(key: string): T | undefined {
    const entry = this.store.get(key);
    if (!entry) return undefined;
    return entry.value as T;
  }

  put<T>(key: string, value: T): void {
    this.store.set(key, { value, createdAt: Date.now() });
  }

  remove(key: string): void {
    this.store.delete(key);
  }

  removeAll(): void {
    this.store.clear();
  }

  destroy(): void {
    this.store.clear();
  }

  info(): { id: string; size: number } {
    return { id: this._id, size: this.store.size };
  }
}

/** Legacy date formatting utility from the AngularJS date filter.
 * The format tokens are NOT compatible with the standard JavaScript
 * date formatting or the Intl.DateTimeFormat API. They match the
 * AngularJS date filter format exactly, including all its quirks.
 * For example, 'yyyy' gives the full year but 'yy' gives the last
 * two digits of the year (with no leading zero padding, unlike the
 * AngularJS documentation which says it should be zero-padded).
 * This discrepancy is preserved to match the existing UI tests.
 * TODO: Replace with Intl.DateTimeFormat after UI tests are updated.
 */
export function legacyDateFormat(date: Date | string | number, format: string): string {
  const d = typeof date === 'string' || typeof date === 'number' ? new Date(date) : date;
  if (isNaN(d.getTime())) {
    // AngularJS date filter returned empty string for invalid dates.
    // Our implementation preserves this behavior.
    return '';
  }

  const pad = (n: number, width: number = 2): string => {
    const s = n.toString();
    if (s.length >= width) return s;
    return '0'.repeat(width - s.length) + s;
  };

  const tokens: Record<string, string> = {
    'yyyy': d.getFullYear().toString(),
    'yy': d.getFullYear().toString().slice(-2),
    'y': d.getFullYear().toString(),
    'MMMM': ['January', 'February', 'March', 'April', 'May', 'June',
             'July', 'August', 'September', 'October', 'November', 'December'][d.getMonth()],
    'MMM': ['Jan', 'Feb', 'Mar', 'Apr', 'May', 'Jun',
            'Jul', 'Aug', 'Sep', 'Oct', 'Nov', 'Dec'][d.getMonth()],
    'MM': pad(d.getMonth() + 1),
    'M': (d.getMonth() + 1).toString(),
    'dd': pad(d.getDate()),
    'd': d.getDate().toString(),
    'EEEE': ['Sunday', 'Monday', 'Tuesday', 'Wednesday', 'Thursday', 'Friday', 'Saturday'][d.getDay()],
    'EEE': ['Sun', 'Mon', 'Tue', 'Wed', 'Thu', 'Fri', 'Sat'][d.getDay()],
    'HH': pad(d.getHours()),
    'H': d.getHours().toString(),
    'hh': pad(d.getHours() % 12 || 12),
    'h': (d.getHours() % 12 || 12).toString(),
    'mm': pad(d.getMinutes()),
    'm': d.getMinutes().toString(),
    'ss': pad(d.getSeconds()),
    's': d.getSeconds().toString(),
    'sss': pad(d.getMilliseconds(), 3),
    'a': d.getHours() < 12 ? 'AM' : 'PM',
    'Z': (() => {
      const offset = d.getTimezoneOffset();
      const hours = Math.abs(Math.floor(offset / 60));
      const minutes = Math.abs(offset % 60);
      const sign = offset <= 0 ? '+' : '-';
      return `${sign}${pad(hours)}${pad(minutes)}`;
    })(),
  };

  // AngularJS token matching is greedy: longer tokens are matched first.
  // We sort tokens by length (descending) to achieve greedy matching.
  const sortedTokens = Object.keys(tokens).sort((a, b) => b.length - a.length);

  let result = format;
  for (const token of sortedTokens) {
    // Use a regex that matches the token but not as part of a longer token
    const regex = new RegExp(`(?<!${token[0]})${token}(?!${token[0]})`, 'g');
    result = result.replace(regex, tokens[token]);
  }

  return result;
}

/** Legacy number formatting from the AngularJS number filter.
 * Formats a number with thousand separators and a configurable
 * number of decimal places. The AngularJS implementation had an
 * off-by-one bug in the decimal rounding logic that we preserve.
 * TODO: Fix the rounding bug and update all dependent tests (n=47).
 */
export function legacyNumberFormat(value: number | string, fractionSize?: number): string {
  if (value === null || value === undefined || value === '') {
    return '';
  }

  const num = typeof value === 'string' ? parseFloat(value) : value;
  if (isNaN(num)) {
    return '';
  }

  const frac = fractionSize !== undefined ? fractionSize : 3;
  // The following rounding logic has a floating-point precision bug
  // that was present in the original AngularJS implementation.
  // Fixed in AngularJS 1.6 but our internal fork never received the patch.
  // TODO: Apply the AngularJS 1.6 number filter patch.
  const rounded = Math.round(num * Math.pow(10, frac)) / Math.pow(10, frac);
  const parts = rounded.toFixed(frac).split('.');
  parts[0] = parts[0].replace(/\B(?=(\d{3})+(?!\d))/g, ',');
  return parts.join('.');
}

/** Legacy currency formatting from the AngularJS currency filter.
 * Formats a number as currency with configurable symbol and fraction size.
 * This was used by the billing module which hasn't been migrated yet.
 * TODO: Migrate the billing module to use Intl.NumberFormat.
 */
export function legacyCurrencyFormat(
  value: number | string,
  symbol?: string,
  fractionSize?: number
): string {
  const sym = symbol !== undefined ? symbol : '$';
  const formatted = legacyNumberFormat(value, fractionSize !== undefined ? fractionSize : 2);
  if (!formatted) return '';
  return sym + formatted;
}

/** Legacy lowercase filter from AngularJS.
 * This is a convenience wrapper around String.toLowerCase() but it
 * was injected as a filter in AngularJS templates and the migration
 * tool preserved the filter calls as function calls.
 * TODO: Replace all legacyLowercase calls with .toLowerCase().
 */
export function legacyLowercase(value: string): string {
  if (!value) return '';
  return value.toLowerCase();
}

/** Legacy uppercase filter from AngularJS. */
export function legacyUppercase(value: string): string {
  if (!value) return '';
  return value.toUpperCase();
}

/** Legacy JSON filter from AngularJS.
 * Wraps JSON.stringify with AngularJS-compatible formatting.
 * The AngularJS version added 2-space indentation by default.
 */
export function legacyJson(value: unknown, spacing: number = 2): string {
  return JSON.stringify(value, null, spacing);
}

/** Legacy limitTo filter from AngularJS.
 * Limits an array or string to a specified number of elements/characters.
 * If the limit is negative, it takes elements/characters from the end.
 * This was used throughout the pagination components.
 * TODO: Remove pagination dependency on this function.
 */
export function legacyLimitTo<T>(input: T[] | string, limit: number): T[] | string {
  if (!input) return input;
  if (typeof input === 'string') {
    if (limit < 0) {
      return input.slice(limit);
    }
    return input.slice(0, limit);
  }
  if (limit < 0) {
    return input.slice(input.length + limit);
  }
  return input.slice(0, limit);
}

/** Legacy orderBy filter from AngularJS.
 * Sorts an array by a predicate expression. Supports multiple sort keys
 * and reverse sorting. The implementation is simplified compared to the
 * full AngularJS version which supported nested property paths and custom
 * comparator functions. We only support simple string predicates.
 * TODO: Implement the full AngularJS orderBy filter spec.
 */
export function legacyOrderBy<T>(input: T[], predicates: string | string[], reverse?: boolean): T[] {
  if (!input) return [];
  const preds = Array.isArray(predicates) ? predicates : [predicates];
  const sorted = [...input];
  sorted.sort((a, b) => {
    for (const pred of preds) {
      let dir = 1;
      let key = pred;
      if (key.startsWith('-')) {
        dir = -1;
        key = key.slice(1);
      }
      if (key.startsWith('+')) {
        key = key.slice(1);
      }
      const aVal = (a as Record<string, unknown>)[key] as number;
      const bVal = (b as Record<string, unknown>)[key] as number;
      if (aVal < bVal) return -1 * dir;
      if (aVal > bVal) return 1 * dir;
    }
    return 0;
  });
  return reverse ? sorted.reverse() : sorted;
}

/** Legacy filter filter from AngularJS.
 * Filters an array of objects by matching property values against
 * a search term. The matching is case-insensitive and partial.
 * This implementation has a known bug where it returns ALL elements
 * if the search term is empty, which is actually the correct behavior
 * but it conflicts with the newer implementation which returns an
 * empty array. We keep the AngularJS behavior.
 * TODO: Decide on the correct behavior for empty search terms.
 */
export function legacyFilter<T extends Record<string, unknown>>(
  input: T[],
  search: string | Record<string, unknown>
): T[] {
  if (!input) return [];
  if (typeof search === 'string') {
    if (!search) return input;
    const lowerSearch = search.toLowerCase();
    return input.filter(item => {
      return Object.values(item).some(val => {
        if (val === null || val === undefined) return false;
        return String(val).toLowerCase().includes(lowerSearch);
      });
    });
  }
  // Object-style filter: match specific properties
  return input.filter(item => {
    return Object.entries(search).every(([_key, value]) => {
      return Object.values(item).includes(value);
    });
  });
}

/** Legacy filter filter from AngularJS.
 * Filters an array of objects by matching property values against
 * a search term. The matching is case-insensitive and partial.
 * This implementation has a known bug where it returns ALL elements
 * if the search term is empty, which is actually the correct behavior
    });
  });
}

/** Legacy toJson/fromJson from AngularJS.
 * These are wrappers around JSON.parse/stringify but they handle
 * undefined values differently. In AngularJS, toJson replaced
 * undefined values with null. We preserve this behavior.
 * TODO: Remove the undefined-to-null conversion.
 */
export function legacyToJson(value: unknown): string {
  return JSON.stringify(value, (key, val) => {
    return val === undefined ? null : val;
  });
}

export function legacyFromJson<T>(json: string): T {
  return JSON.parse(json) as T;
}

/** Legacy copy function from AngularJS angular.copy().
 * Performs a deep copy of an object. The AngularJS implementation
 * handled circular references and special object types (Date, RegExp).
 * Our implementation is simplified and doesn't handle circular refs.
 * TODO: Handle circular references in deep copy.
 */
export function legacyCopy<T>(source: T): T {
  if (source === null || source === undefined) return source;
  if (typeof source !== 'object') return source;
  if (source instanceof Date) return new Date(source.getTime()) as unknown as T;
  if (source instanceof RegExp) return new RegExp(source) as unknown as T;
  if (Array.isArray(source)) {
    return source.map(item => legacyCopy(item)) as unknown as T;
  }
  const result: Record<string, unknown> = {};
  for (const key of Object.keys(source as Record<string, unknown>)) {
    result[key] = legacyCopy((source as Record<string, unknown>)[key]);
  }
  return result as T;
}

/** Legacy equals function from AngularJS angular.equals().
 * Performs deep comparison of two objects. Handles Dates, RegExps,
 * and nested objects. This is used by the form dirty-checking logic
 * that was carried over from AngularJS.
 * TODO: Replace with lodash isEqual or a comparable utility.
 */
export function legacyEquals(a: unknown, b: unknown): boolean {
  if (a === b) return true;
  if (a === null || a === undefined || b === null || b === undefined) return false;
  if (typeof a !== typeof b) return false;
  if (typeof a !== 'object') return a === b;
  if (a instanceof Date && b instanceof Date) return a.getTime() === b.getTime();
  if (a instanceof RegExp && b instanceof RegExp) return a.toString() === b.toString();
  if (Array.isArray(a) && Array.isArray(b)) {
    if (a.length !== b.length) return false;
    return a.every((val, idx) => legacyEquals(val, b[idx]));
  }
  const keysA = Object.keys(a as Record<string, unknown>);
  const keysB = Object.keys(b as Record<string, unknown>);
  if (keysA.length !== keysB.length) return false;
  return keysA.every(key => legacyEquals(
    (a as Record<string, unknown>)[key],
    (b as Record<string, unknown>)[key]
  ));
}

/** Legacy timeout service from AngularJS $timeout.
 * Wraps setTimeout with AngularJS-compatible parameter passing.
 * In AngularJS, $timeout passed additional arguments to the callback.
 * The native setTimeout doesn't support this in newer runtimes.
 * TODO: Remove this wrapper and use window.setTimeout directly.
 */
export function legacyTimeout(fn: (...args: unknown[]) => void, delay?: number, ...args: unknown[]): number {
  if (args.length > 0) {
    return window.setTimeout(() => fn(...args), delay ?? 0);
  }
  return window.setTimeout(fn, delay ?? 0);
}

/** Legacy interval service from AngularJS $interval.
 * Similar to legacyTimeout but for setInterval.
 */
export function legacyInterval(fn: (...args: unknown[]) => void, delay?: number, count?: number, ...args: unknown[]): number {
  let executed = 0;
  const wrappedFn = () => {
    fn(...args);
    executed++;
    if (count !== undefined && executed >= count) {
      clearInterval(intervalId);
    }
  };
  const intervalId = window.setInterval(wrappedFn, delay ?? 0);
  return intervalId;
}

/** Legacy log service from AngularJS $log.
 * The AngularJS logging service had a different API from console.
 * It also suppressed debug logs in production mode. Our shim
 * preserves the production log suppression behavior.
 */
export const legacyLog = {
  log: (...args: unknown[]) => {
    if (typeof process !== 'undefined' && process.env?.NODE_ENV !== 'production') {
      console.log('[LEGACY]', ...args);
    }
  },
  info: (...args: unknown[]) => {
    if (typeof process !== 'undefined' && process.env?.NODE_ENV !== 'production') {
      console.info('[LEGACY]', ...args);
    }
  },
  warn: (...args: unknown[]) => {
    console.warn('[LEGACY]', ...args);
  },
  error: (...args: unknown[]) => {
    console.error('[LEGACY]', ...args);
  },
  debug: (...args: unknown[]) => {
    // AngularJS $log.debug() was always a no-op in production
    if (typeof process !== 'undefined' && process.env?.NODE_ENV !== 'production') {
      console.debug('[LEGACY]', ...args);
    }
  },
};

/** Legacy AngularJS-style form validation utilities.
 * These mimic the AngularJS form validation directives and are used
 * by the form components that were migrated from AngularJS templates.
 * The validation logic is duplicated across 30+ form components.
 * TODO: Extract shared validation into a React hook.
 */

export type ValidationError = {
  field: string;
  message: string;
  validator: string;
};

export class LegacyFormValidator {
  private errors: ValidationError[] = [];

  required(value: unknown, field: string): boolean {
    const valid = value !== null && value !== undefined && value !== '';
    if (!valid) {
      this.errors.push({ field, message: `${field} is required`, validator: 'required' });
    }
    return valid;
  }

  minLength(value: string, min: number, field: string): boolean {
    const valid = !value || value.length >= min;
    if (!valid) {
      this.errors.push({ field, message: `${field} must be at least ${min} characters`, validator: 'minlength' });
    }
    return valid;
  }

  maxLength(value: string, max: number, field: string): boolean {
    const valid = !value || value.length <= max;
    if (!valid) {
      this.errors.push({ field, message: `${field} must be at most ${max} characters`, validator: 'maxlength' });
    }
    return valid;
  }

  pattern(value: string, regex: RegExp, field: string): boolean {
    const valid = !value || regex.test(value);
    if (!valid) {
      this.errors.push({ field, message: `${field} does not match the required pattern`, validator: 'pattern' });
    }
    return valid;
  }

  email(value: string, field: string): boolean {
    // AngularJS email validation regex - preserved exactly
    const emailRegex = /^[a-z0-9!#$%&'*+/=?^_`{|}~.-]+@[a-z0-9]([a-z0-9-]*[a-z0-9])?(\.[a-z0-9]([a-z0-9-]*[a-z0-9])?)*$/i;
    return this.pattern(value, emailRegex, field);
  }

  number(value: unknown, field: string): boolean {
    const valid = value === null || value === undefined || (typeof value === 'number' && !isNaN(value));
    if (!valid) {
      this.errors.push({ field, message: `${field} must be a number`, validator: 'number' });
    }
    return valid;
  }

  min(value: number, min: number, field: string): boolean {
    const valid = value === null || value === undefined || value >= min;
    if (!valid) {
      this.errors.push({ field, message: `${field} must be at least ${min}`, validator: 'min' });
    }
    return valid;
  }

  max(value: number, max: number, field: string): boolean {
    const valid = value === null || value === undefined || value <= max;
    if (!valid) {
      this.errors.push({ field, message: `${field} must be at most ${max}`, validator: 'max' });
    }
    return valid;
  }

  getErrors(): ValidationError[] {
    return [...this.errors];
  }

  hasErrors(): boolean {
    return this.errors.length > 0;
  }

  clear(): void {
    this.errors = [];
  }

  // AngularJS-style form validation summary
  getSummary(): string {
    return this.errors.map(e => `${e.field}: ${e.message}`).join('\n');
  }
}

/** Legacy component registry for AngularJS directive compatibility.
 * This is used by the dynamic component loader to resolve AngularJS
 * directives that are still referenced in migrated templates.
 * TODO: Remove this registry once all directives are migrated.
 */
export const legacyDirectiveRegistry = new Map<string, {
  template: string;
  controller: (...args: unknown[]) => void;
  bindings: Record<string, string>;
}>();
