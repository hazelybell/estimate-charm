MIME-Version: 1.0 
Content-type: multipart/mixed; boundary=boundary

--boundary
Content-disposition: inline
Content-type: text/plain; charset=utf-8

This should be added to the description.

--boundary
Content-disposition: inline
Content-type: text/plain; charset=utf-8

This should be added as a comment.

--boundary
Content-disposition: attachment; filename='attachment1'
Content-type: text/plain; charset=utf-8

This is an attachment.

--boundary
Content-disposition: inline
Content-type: text/plain; charset=utf-8

This should be added as another comment.

--boundary
Content-disposition: attachment; filename='attachment2'
Content-description: Attachment description.
Content-Transfer-Encoding: base64
Content-Type: application/x-gzip

H4sICH5op0UAA3Rlc3QudHh0AAvJyCxWAKLEvPySjNQihcSSksTkjNzUvBIdhfLMkgyFRIWU1OLk
osyCksz8PD0uAPiw9nkwAAAA

--boundary--
