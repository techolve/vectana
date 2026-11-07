"use client";

import { Suspense, useState } from "react";
import { useSearchParams } from "next/navigation";
import { PencilIcon, PlusIcon } from "lucide-react";
import { toast } from "sonner";
import { useTranslations } from "next-intl";

import { Link, useRouter } from "@/i18n/navigation";
import { api, dealAmount, yen, type Contact, type CustomerDetail, type Project } from "@/lib/api";
import { useApi } from "@/lib/hooks";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Card, CardAction, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Checkbox } from "@/components/ui/checkbox";
import { Dialog, DialogContent, DialogFooter, DialogHeader, DialogTitle } from "@/components/ui/dialog";
import { Field, FieldGroup, FieldLabel } from "@/components/ui/field";
import { Input } from "@/components/ui/input";
import { Textarea } from "@/components/ui/textarea";
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from "@/components/ui/table";
import { Empty, ErrorText, LabeledField, PageHeader } from "@/components/common";
import { usePageCrumb } from "@/components/app-shell";
import { ProjectStatusBadge, shortDate, userLabel } from "@/components/sales/status";
import { UserSelect } from "@/components/sales/user-select";

function CustomerDetailView() {
  const t = useTranslations();
  const id = useSearchParams().get("id");
  const router = useRouter();
  const { data: c, error, reload } = useApi<CustomerDetail>(id ? `/customers/${id}` : null);
  const { data: projects } = useApi<Project[]>(id ? `/projects?customer_id=${id}` : null);
  const [editing, setEditing] = useState(false);
  const [contact, setContact] = useState<Contact | "new" | null>(null);
  usePageCrumb(c?.name);

  if (!id) return <ErrorText>{t("customers.notSpecified")}</ErrorText>;
  if (error) return <ErrorText>{error}</ErrorText>;
  if (!c) return null;

  async function remove() {
    if (!c || !confirm(t("customers.confirmDelete", { name: c.name }))) return;
    try {
      await api(`/customers/${c.id}`, { method: "DELETE" });
      router.replace("/customers/");
    } catch (e) {
      toast.error((e as Error).message);
    }
  }

  const info: [string, React.ReactNode][] = [
    [t("customers.address"), c.address],
    [t("customers.phone"), c.phone],
    [t("customers.paymentTerms"), c.payment_terms],
    [t("customers.billingContact"), c.billing_contact],
    [t("customers.website"), c.website],
  ];

  return (
    <>
      <PageHeader
        title={c.name}
        description={[c.industry, c.sales_owner && t("customers.ownerLine", { name: userLabel(c.sales_owner) })]
          .filter(Boolean)
          .join(" ・ ")}
        actions={
          c.can_edit && (
            <>
              <Button variant="outline" onClick={() => setEditing(true)}>
                <PencilIcon /> {t("common.edit")}
              </Button>
              <Button nativeButton={false} render={<Link href={{ pathname: "/projects/", query: { new: "1", customer: c.id } }} />}>
                <PlusIcon /> {t("customers.newProject")}
              </Button>
            </>
          )
        }
      />
      <div className="grid gap-4 lg:grid-cols-[minmax(0,1fr)_minmax(0,1.6fr)]">
        <Card>
          <CardHeader>
            <CardTitle>{t("customers.info")}</CardTitle>
          </CardHeader>
          <CardContent className="divide-y text-sm">
            {info.map(([label, value]) => (
              <div key={label} className="grid grid-cols-[7rem_1fr] gap-2 py-1.5">
                <span className="text-muted-foreground">{label}</span>
                <span className="break-words">{value || "—"}</span>
              </div>
            ))}
            {c.notes && <p className="pt-2 whitespace-pre-wrap text-muted-foreground">{c.notes}</p>}
          </CardContent>
        </Card>
        <Card>
          <CardHeader>
            <CardTitle>{t("customers.contacts")}</CardTitle>
            {c.can_edit && (
              <CardAction>
                <Button variant="outline" size="sm" onClick={() => setContact("new")}>
                  <PlusIcon /> {t("customers.addContact")}
                </Button>
              </CardAction>
            )}
          </CardHeader>
          <CardContent>
            {c.contacts.length === 0 ? (
              <p className="text-sm text-muted-foreground">{t("customers.noContacts")}</p>
            ) : (
              <Table>
                <TableHeader>
                  <TableRow>
                    <TableHead>{t("customers.contactName")}</TableHead>
                    <TableHead>{t("customers.contactTitle")}</TableHead>
                    <TableHead>{t("customers.email")}</TableHead>
                    <TableHead>{t("customers.phone")}</TableHead>
                    <TableHead />
                  </TableRow>
                </TableHeader>
                <TableBody>
                  {c.contacts.map((x) => (
                    <TableRow key={x.id}>
                      <TableCell>
                        {x.name}
                        {x.is_primary && (
                          <Badge variant="secondary" className="ml-2">
                            {t("customers.primary")}
                          </Badge>
                        )}
                      </TableCell>
                      <TableCell className="text-xs">{x.title ?? "—"}</TableCell>
                      <TableCell className="text-xs">{x.email ?? "—"}</TableCell>
                      <TableCell className="text-xs">{x.phone ?? "—"}</TableCell>
                      <TableCell className="text-right">
                        {c.can_edit && (
                          <Button variant="outline" size="sm" onClick={() => setContact(x)}>
                            {t("common.edit")}
                          </Button>
                        )}
                      </TableCell>
                    </TableRow>
                  ))}
                </TableBody>
              </Table>
            )}
          </CardContent>
        </Card>
      </div>

      <h2 className="mt-8 mb-1 text-base font-semibold">{t("customers.projectsTitle")}</h2>
      <p className="mb-3 text-xs text-muted-foreground">{t("customers.projectsHint")}</p>
      {projects &&
        (projects.length === 0 ? (
          <Empty>{t("customers.noProjects")}</Empty>
        ) : (
          <Table>
            <TableHeader>
              <TableRow>
                <TableHead>{t("projects.name")}</TableHead>
                <TableHead>{t("projects.status")}</TableHead>
                <TableHead className="text-right">{t("projects.amount")}</TableHead>
                <TableHead>{t("customers.estimates")}</TableHead>
                <TableHead>{t("projects.nextAction")}</TableHead>
              </TableRow>
            </TableHeader>
            <TableBody>
              {projects.map((p) => (
                <TableRow key={p.id}>
                  <TableCell>
                    <Link href={{ pathname: "/projects/detail/", query: { id: p.id } }} className="font-medium hover:underline">
                      {p.name}
                    </Link>
                  </TableCell>
                  <TableCell>
                    <ProjectStatusBadge status={p.status} />
                  </TableCell>
                  <TableCell className="text-right tabular-nums">
                    {p.monthly_amount != null
                      ? t("projects.perMonth", { amount: yen(p.monthly_amount) })
                      : yen(p.is_deal ? dealAmount(p) : p.won_amount)}
                  </TableCell>
                  <TableCell className="text-xs">{t("customers.estimateCount", { count: p.estimate_count ?? 0 })}</TableCell>
                  <TableCell className="text-xs">
                    {p.status === "lost" ? p.lost_reason ?? "—" : p.next_action ? `${p.next_action} ${shortDate(p.next_action_on)}` : "—"}
                  </TableCell>
                </TableRow>
              ))}
            </TableBody>
          </Table>
        ))}

      {c.can_edit && (
        <div className="mt-10">
          <Button variant="ghost" className="text-destructive" onClick={remove}>
            {t("customers.delete")}
          </Button>
        </div>
      )}
      {editing && (
        <EditCustomerDialog
          customer={c}
          onClose={() => setEditing(false)}
          onSaved={() => {
            setEditing(false);
            reload();
          }}
        />
      )}
      {contact && (
        <ContactDialog
          customerId={c.id}
          contact={contact === "new" ? null : contact}
          onClose={() => setContact(null)}
          onSaved={() => {
            setContact(null);
            reload();
          }}
        />
      )}
    </>
  );
}

function EditCustomerDialog({ customer, onClose, onSaved }: { customer: CustomerDetail; onClose: () => void; onSaved: () => void }) {
  const t = useTranslations();
  const [form, setForm] = useState({
    name: customer.name,
    industry: customer.industry ?? "",
    address: customer.address ?? "",
    phone: customer.phone ?? "",
    website: customer.website ?? "",
    payment_terms: customer.payment_terms ?? "",
    billing_contact: customer.billing_contact ?? "",
    notes: customer.notes ?? "",
  });
  const [owner, setOwner] = useState(customer.sales_owner?.id ?? "");
  const set = (key: keyof typeof form) => (e: React.ChangeEvent<HTMLInputElement | HTMLTextAreaElement>) =>
    setForm({ ...form, [key]: e.target.value });

  async function save(e: React.FormEvent) {
    e.preventDefault();
    try {
      await api(`/customers/${customer.id}`, {
        method: "PATCH",
        json: {
          ...Object.fromEntries(Object.entries(form).map(([k, v]) => [k, v.trim() || null])),
          name: form.name,
          sales_owner_id: owner || null,
        },
      });
      toast.success(t("common.saved"));
      onSaved();
    } catch (err) {
      toast.error((err as Error).message);
    }
  }

  const fields: [keyof typeof form, string][] = [
    ["industry", t("customers.industry")],
    ["address", t("customers.address")],
    ["phone", t("customers.phone")],
    ["website", t("customers.website")],
    ["payment_terms", t("customers.paymentTerms")],
    ["billing_contact", t("customers.billingContact")],
  ];

  return (
    <Dialog open onOpenChange={(o) => !o && onClose()}>
      <DialogContent className="max-h-[90vh] max-w-2xl overflow-y-auto">
        <DialogHeader>
          <DialogTitle>{t("customers.editTitle")}</DialogTitle>
        </DialogHeader>
        <form onSubmit={save}>
          <FieldGroup>
            <div className="grid gap-4 sm:grid-cols-2">
              <LabeledField label={t("customers.name")} htmlFor="c-name">
                <Input id="c-name" required value={form.name} onChange={set("name")} />
              </LabeledField>
              <LabeledField label={t("customers.salesOwner")}>
                <UserSelect value={owner} onChange={setOwner} current={customer.sales_owner} />
              </LabeledField>
              {fields.map(([key, label]) => (
                <LabeledField key={key} label={label} htmlFor={`c-${key}`}>
                  <Input id={`c-${key}`} value={form[key]} onChange={set(key)} />
                </LabeledField>
              ))}
            </div>
            <LabeledField label={t("customers.notes")} htmlFor="c-notes">
              <Textarea id="c-notes" value={form.notes} onChange={set("notes")} />
            </LabeledField>
            <DialogFooter>
              <Button type="submit">{t("common.save")}</Button>
            </DialogFooter>
          </FieldGroup>
        </form>
      </DialogContent>
    </Dialog>
  );
}

function ContactDialog({
  customerId,
  contact,
  onClose,
  onSaved,
}: {
  customerId: string;
  contact: Contact | null;
  onClose: () => void;
  onSaved: () => void;
}) {
  const t = useTranslations();
  const [name, setName] = useState(contact?.name ?? "");
  const [title, setTitle] = useState(contact?.title ?? "");
  const [email, setEmail] = useState(contact?.email ?? "");
  const [phone, setPhone] = useState(contact?.phone ?? "");
  const [primary, setPrimary] = useState(contact?.is_primary ?? false);
  const [error, setError] = useState<string | null>(null);
  const base = `/customers/${customerId}/contacts`;

  async function save(e: React.FormEvent) {
    e.preventDefault();
    const json = { name, title: title || null, email: email || null, phone: phone || null, is_primary: primary };
    try {
      await api(contact ? `${base}/${contact.id}` : base, { method: contact ? "PUT" : "POST", json });
      onSaved();
    } catch (err) {
      setError((err as Error).message);
    }
  }

  async function remove() {
    if (!contact) return;
    await api(`${base}/${contact.id}`, { method: "DELETE" });
    onSaved();
  }

  return (
    <Dialog open onOpenChange={(o) => !o && onClose()}>
      <DialogContent>
        <DialogHeader>
          <DialogTitle>{contact ? t("customers.editContact") : t("customers.addContact")}</DialogTitle>
        </DialogHeader>
        <form onSubmit={save}>
          <FieldGroup>
            <LabeledField label={t("customers.contactName")} htmlFor="ct-name">
              <Input id="ct-name" required value={name} onChange={(e) => setName(e.target.value)} />
            </LabeledField>
            <LabeledField label={t("customers.contactTitle")} htmlFor="ct-title">
              <Input id="ct-title" value={title} onChange={(e) => setTitle(e.target.value)} />
            </LabeledField>
            <div className="grid gap-4 sm:grid-cols-2">
              <LabeledField label={t("customers.email")} htmlFor="ct-email">
                <Input id="ct-email" type="email" value={email} onChange={(e) => setEmail(e.target.value)} />
              </LabeledField>
              <LabeledField label={t("customers.phone")} htmlFor="ct-phone">
                <Input id="ct-phone" value={phone} onChange={(e) => setPhone(e.target.value)} />
              </LabeledField>
            </div>
            <Field orientation="horizontal">
              <Checkbox id="ct-primary" checked={primary} onCheckedChange={(v) => setPrimary(v === true)} />
              <FieldLabel htmlFor="ct-primary" className="font-normal">
                {t("customers.primaryLabel")}
              </FieldLabel>
            </Field>
            <ErrorText>{error}</ErrorText>
            <DialogFooter className="sm:justify-between">
              {contact ? (
                <Button type="button" variant="ghost" className="text-destructive" onClick={remove}>
                  {t("common.delete")}
                </Button>
              ) : (
                <span />
              )}
              <Button type="submit">{t("common.save")}</Button>
            </DialogFooter>
          </FieldGroup>
        </form>
      </DialogContent>
    </Dialog>
  );
}

export default function CustomerDetailPage() {
  return (
    <Suspense>
      <CustomerDetailView />
    </Suspense>
  );
}
