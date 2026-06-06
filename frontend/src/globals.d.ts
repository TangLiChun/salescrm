export {};

declare global {
  type AnyRecord = Record<string, any>;

  interface Window {
    t: (key: string, params?: Record<string, unknown>) => string;
  }

  const t: (key: string, params?: Record<string, unknown>) => string;

  interface EventTarget {
    checked: boolean;
    closest(selectors: string): Element | null;
    dataset: DOMStringMap;
    disabled: boolean;
    indeterminate: boolean;
    placeholder: string;
    reset(): void;
    title: string;
    value: any;
  }

  interface Element {
    checked: boolean;
    dataset: DOMStringMap;
    disabled: boolean;
    focus(): void;
    indeterminate: boolean;
    offsetParent: Element | null;
    placeholder: string;
    reset(): void;
    requestSubmit(): void;
    style: CSSStyleDeclaration;
    title: string;
    value: any;
  }

  interface HTMLElement {
    _piChannelState?: AnyRecord;
    _piDiscoverState?: AnyRecord;
    _piLeads?: AnyRecord[];
    _piLookupRows?: AnyRecord[];
  }
}
