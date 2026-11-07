import { z } from "zod";

import { defineTool, given, id } from "./define.ts";

const customerFields = {
  industry: z.string().nullable().optional(),
  address: z.string().nullable().optional(),
  phone: z.string().nullable().optional(),
  website: z.string().nullable().optional(),
  payment_terms: z.string().nullable().optional().describe("e.g. 月末締め翌月末払い"),
  billing_contact: z.string().nullable().optional(),
  notes: z.string().nullable().optional(),
  sales_owner_id: id("Sales owner user").nullable().optional(),
};

export const customerTools = [
  defineTool({
    name: "list_customers",
    title: "List customers",
    description: "Customers (client companies) the user can see. Not available to partner (BP) users.",
    input: {
      q: z.string().default("").describe("Part of the name"),
      company_id: id("Company").optional(),
    },
    run: (args, c) => c.get("/api/customers", args),
  }),
  defineTool({
    name: "get_customer",
    title: "Customer details",
    description: "One customer with its contacts and projects.",
    input: { customer_id: id("Customer") },
    run: ({ customer_id }, c) => c.get(`/api/customers/${customer_id}`),
  }),
  defineTool({
    name: "create_customer",
    title: "Create a customer",
    description: "Register a customer. Needs the sales role or company admin.",
    write: true,
    input: {
      name: z.string().min(1).max(200),
      company_id: id("Company").optional().describe("Default: the user's company"),
      ...customerFields,
    },
    run: (args, c) => c.post("/api/customers", given(args)),
  }),
  defineTool({
    name: "update_customer",
    title: "Update a customer",
    description: "Change a customer's fields. Only the fields you pass change; null clears a field.",
    write: true,
    idempotent: true,
    input: {
      customer_id: id("Customer"),
      name: z.string().min(1).max(200).optional(),
      ...customerFields,
    },
    run: ({ customer_id, ...body }, c) => c.patch(`/api/customers/${customer_id}`, given(body)),
  }),
  defineTool({
    name: "add_customer_contact",
    title: "Add a customer contact",
    description: "Add a contact person to a customer.",
    write: true,
    input: {
      customer_id: id("Customer"),
      name: z.string().min(1).max(200),
      title: z.string().nullable().optional().describe("Job title or department"),
      email: z.string().nullable().optional(),
      phone: z.string().nullable().optional(),
      is_primary: z.boolean().default(false),
    },
    run: ({ customer_id, ...body }, c) =>
      c.post(`/api/customers/${customer_id}/contacts`, given(body)),
  }),
];
