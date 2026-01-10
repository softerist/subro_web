/** @vitest-environment jsdom */
import React from "react";
import { render, screen, cleanup, act } from "@testing-library/react";
import { describe, it, expect, afterEach, vi } from "vitest";
import * as matchers from "@testing-library/jest-dom/matchers";
expect.extend(matchers);

import {
  Select,
  SelectContent,
  SelectGroup,
  SelectItem,
  SelectLabel,
  SelectSeparator,
  SelectTrigger,
  SelectValue,
} from "@/components/ui/select";
import {
  Table,
  TableBody,
  TableCaption,
  TableCell,
  TableFooter,
  TableHead,
  TableHeader,
  TableRow,
} from "@/components/ui/table";
import {
  Card,
  CardHeader,
  CardTitle,
  CardDescription,
  CardContent,
  CardFooter,
} from "@/components/ui/card";
import {
  Form,
  FormField,
  FormItem,
  FormLabel,
  FormControl,
  FormDescription,
  FormMessage,
  useFormField,
} from "@/components/ui/form";
import { useForm } from "react-hook-form";

describe("UI Components Coverage", () => {
  afterEach(() => {
    cleanup();
  });

  describe("Select Component", () => {
    it("renders SelectLabel and SelectSeparator", () => {
      // Basic rendering of Select components to cover Label and Separator
      // Radix Select parts usually need to be inside Root/Content, but for pure coverage of the React component wrapper,
      // we might be able to render them directly if they don't depend on Context strictly or if we provide basic Context.
      // However, Radix Primitives often error without context.
      // Let's render a full Select structure.

      render(
        <Select open>
          <SelectTrigger>
            <SelectValue placeholder="Select" />
          </SelectTrigger>
          <SelectContent>
            <SelectGroup>
              <SelectLabel>My Label</SelectLabel>
              <SelectSeparator />
              <SelectItem value="1">Item 1</SelectItem>
            </SelectGroup>
          </SelectContent>
        </Select>,
      );

      // SelectContent renders in a Portal by default?
      // Yes, line 72 of select.tsx uses SelectPrimitive.Portal.
      // So we look for them in document.body.

      expect(screen.getByText("My Label")).toBeInTheDocument();
      // Separator usually has role="separator"
      // Separator usually has role="separator" but Radix might hide it or use presentation
      // The output shows it has aria-hidden="true" and class "bg-muted".
      // We can query by simple class check in the document body since it's in a portal.
      const separator = document.body.querySelector(".bg-muted");
      expect(separator).toBeInTheDocument();
    });
  });

  describe("Table Component", () => {
    it("renders TableFooter and TableCaption", () => {
      render(
        <Table>
          <TableCaption>List of users</TableCaption>
          <TableHeader>
            <TableRow>
              <TableHead>Name</TableHead>
            </TableRow>
          </TableHeader>
          <TableBody>
            <TableRow>
              <TableCell>John</TableCell>
            </TableRow>
          </TableBody>
          <TableFooter>
            <TableRow>
              <TableCell>Total: 1</TableCell>
            </TableRow>
          </TableFooter>
        </Table>,
      );

      expect(screen.getByText("List of users")).toBeInTheDocument(); // Caption
      expect(screen.getByText("Total: 1")).toBeInTheDocument(); // Inside Footer

      // Verify structure (optional, but good for verification)
      const caption = screen.getByText("List of users");
      expect(caption.tagName.toLowerCase()).toBe("caption");

      const footerCell = screen.getByText("Total: 1").closest("tfoot");
      expect(footerCell).toBeInTheDocument();
    });
  });

  describe("Card Component", () => {
    it("forwards refs and merges classNames across sections", () => {
      const cardRef = React.createRef<HTMLDivElement>();
      const footerRef = React.createRef<HTMLDivElement>();

      render(
        <Card ref={cardRef} className="custom-card">
          <CardHeader>
            <CardTitle>Card Title</CardTitle>
            <CardDescription>Card description</CardDescription>
          </CardHeader>
          <CardContent>Body content</CardContent>
          <CardFooter ref={footerRef} className="custom-footer">
            Footer content
          </CardFooter>
        </Card>,
      );

      expect(cardRef.current).toBeInstanceOf(HTMLDivElement);
      expect(cardRef.current?.className).toContain("custom-card");
      expect(screen.getByText("Card Title")).toBeInTheDocument();
      expect(screen.getByText("Card description")).toBeInTheDocument();
      expect(screen.getByText("Body content")).toBeInTheDocument();
      const footer = screen.getByText("Footer content");
      expect(footerRef.current).toBeInstanceOf(HTMLDivElement);
      expect(footerRef.current?.textContent).toContain("Footer content");
      expect(footerRef.current?.className).toContain("custom-footer");
    });
  });

  describe("Form Components", () => {
    const FormWrapper = ({
      onReady,
    }: {
      onReady?: (methods: ReturnType<typeof useForm>) => void;
    }) => {
      const methods = useForm<{ email: string }>({
        defaultValues: { email: "" },
      });
      React.useEffect(() => {
        onReady?.(methods);
      }, [methods, onReady]);

      return (
        <Form {...methods}>
          <form>
            <FormField
              control={methods.control}
              name="email"
              rules={{ required: "Required" }}
              render={({ field }) => (
                <FormItem>
                  <FormLabel>Email</FormLabel>
                  <FormControl>
                    <input placeholder="email" {...field} />
                  </FormControl>
                  <FormDescription>Description text</FormDescription>
                  <FormMessage>Required</FormMessage>
                </FormItem>
              )}
            />
          </form>
        </Form>
      );
    };

    it("sets aria props and renders message when error exists", async () => {
      let methods: ReturnType<typeof useForm> | undefined;
      render(<FormWrapper onReady={(m) => (methods = m)} />);
      await act(async () => {
        await methods?.trigger();
      });
      const input = screen.getByPlaceholderText("email");
      expect(input).toHaveAttribute("aria-invalid", "true");

      const describedBy = input.getAttribute("aria-describedby") || "";
      expect(describedBy.includes("-form-item-description")).toBe(true);
      expect(describedBy.includes("-form-item-message")).toBe(true);
      const messageId = describedBy
        .split(" ")
        .find((id) => id.includes("-form-item-message"));
      expect(messageId && document.getElementById(messageId)).toBeTruthy();
    });

    it("omits message and aria message id when no error", () => {
      render(<FormWrapper />);
      const input = screen.getByPlaceholderText("email");
      expect(input).toHaveAttribute("aria-invalid", "false");
      const describedBy = input.getAttribute("aria-describedby") || "";
      expect(describedBy.includes("-form-item-message")).toBe(false);
      expect(screen.queryByText("Required")).toBeNull();
    });

    it("throws when FormField context is missing", () => {
      // Suppress logging of the expected error
      const consoleSpy = vi
        .spyOn(console, "error")
        .mockImplementation(() => {});
      const errorHandler = vi.fn((event: ErrorEvent) => {
        event.preventDefault();
      });
      window.addEventListener("error", errorHandler);

      class ErrorBoundary extends React.Component<
        { children: React.ReactNode },
        { error: Error | null }
      > {
        state = { error: null };

        static getDerivedStateFromError(error: Error) {
          return { error };
        }

        render() {
          if (this.state.error) {
            return <div>{this.state.error.message}</div>;
          }
          return this.props.children;
        }
      }

      const MissingProvider = () => {
        useFormField();
        return null;
      };

      render(
        <ErrorBoundary>
          <MissingProvider />
        </ErrorBoundary>,
      );

      expect(
        screen.getByText("useFormField should be used within <FormField>"),
      ).toBeInTheDocument();

      expect(errorHandler).toHaveBeenCalled();
      window.removeEventListener("error", errorHandler);
      consoleSpy.mockRestore();
    });
  });
});
