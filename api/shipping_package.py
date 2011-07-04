# -*- coding: utf-8 -*-
"""
    shipping_package

    :copyright: (c) 2011 by Openlabs Technologies & Consulting (P) Limited
    :copyright: (c) 2010 by Sharoon Thomas.
    :copyright: (c) 2011 by United Parcel Service of America (Documentation)
    :license: AGPL, see LICENSE for more details.

    Shipping Package XML API
    ~~~~~~~~~~~~~~~~~~~~~~~~

    .. note::
        The documentation is partly extracted from the UPS Developer guide and
        is hence covered by the copyright of United Parcel Service of America

    The Shipping API makes UPS shipping services available to client 
    applications that communicate with UPS using the Internet. With this API, 
    applications can prepare or schedule small package shipments, manage 
    returns, or cancel previously scheduled shipments.

    Two Step (Phase) Shipping Process
    ---------------------------------

    The process to use the Shipping API consists of two phases, the `ship 
    confirm` phase followed by the `ship accept` phase. An XML request/response
    pair is exchanged between the client and server in each phase. The XML 
    messages exchanged in the confirm phase are the ShipmentConfirmRequest 
    input message and the ShipmentConfirmResponse output message. This is 
    implemented in :class:`ShipmentConfirm`.

    The XML messages exchanged in the accept phase are the 
    ShipmentAcceptRequest input message and the ShipmentAcceptResponse output
    message. Shipment information is specified in the ShipmentConfirmRequest 
    message. After the ShipmentConfirmRequest message is created, it must be 
    sent to the Shipping API ShipConfirm URL address, using a HTTP POST. 

    After the ShipmentConfirmRequest message is received by the server, it is 
    preprocessed and validated. If the ShipmentConfirmRequest message passes 
    all validation tests, a ShipmentConfirmResponse message is returned 
    containing basic rate information, the shipment Id, and the shipment digest
    which can be extracted from the response using 
    :meth:`ShipmentConfirm.extract_digest`.

    If the ShipmentConfirmRequest message fails validation, a 
    ShipmentConfirmResponse message is returned containing error information. 
    In the event of such an error, an exception is raised.

    .. note::
        The majority of the validation is performed in this phase but the 
        actual shipment has not been created at this point.

    In order to create a shipment and receive the shipping label(s), a 
    ShipAcceptRequest message must be created and sent to the Shipping API 
    ShipAccept connection address URL, using a HTTP POST. This API is 
    implemented in the class :class:`ShipmentAccept`.

    The ShipAcceptRequest message must contain the shipment digest returned in 
    the ShipmentConfirmResponse message and can be passed as an argument to
    :meth:`SipmentAccept.shipment_accept_request_type` method. 
    
    After the ShipmentAcceptRequest message is received in the UPS server, 
    additional processing validation is performed. If the ShipmentAcceptRequest
    message passes all validation tests, a ShipmentAcceptResponse message is 
    returned containing detailed rate information, the Shipment Id, package 
    tracking numbers and the shipping label(s).

    If the ShipmentAcceptRequest message fails validation, a 
    ShipmentAcceptResponse message is returned containing error information. As
    in the :class:`ShipmentConfirm` API an exception is raised.


"""
from __future__ import with_statement

from logging import getLogger, StreamHandler, Formatter, getLoggerClass, DEBUG
from threading import Lock
import urllib2

from lxml import etree, objectify
from lxml.builder import E


_logger_lock = Lock()


class PyUPSException(Exception): pass


def not_implemented_yet(func):
    """A decorator function which raises the `NotImplementedYet` error
    for the given function.
    """
    def wrapper(*args, **kwargs):
        raise Exception('%s is not Implemented yet' % func.__name__)
    return wrapper


class BaseAPIClient(object):
    """Base client which also works as a context processor
    """

    base_url = {
        'sandbox': "https://wwwcie.ups.com/ups.app/xml",
        'production': "https://www.ups.com/ups.app/xml/"
        }

    #: The logging format used for the debug logger.  This is only used when
    #: the application is in debug mode, otherwise the attached logging
    #: handler does the formatting.
    #: 
    #: :copyright: (c) 2010 by Armin Ronacher.
    debug_log_format = (
        '-' * 80 + '\n' +
        '%(levelname)s in %(module)s [%(pathname)s:%(lineno)d]:\n' +
        '%(message)s\n' +
        '-' * 80
    )

    def __init__(self, license_no, user_id, password, sandbox):
        """
        :param license_no: Access License No/Key
        :param user_id: API user ID, Usually your UPS accoutn login
        :param password: API Password,Usually UPS account Password
        :param sandbox: True if supposed to work in test mode
        """
        self.license_no = license_no
        self.user_id = user_id
        self.password = password
        self.sandbox = sandbox

        #: Prepare the lazy setup of the logger.
        self._logger = None
        self.logger_name = 'PyUPS'

    def create_logger(self):
        """Creates a logger.  This logger works similar to a regular Python 
        logger but changes the effective logging level based on the API's 
        sandbox flag.
        Furthermore this function also removes all attached handlers in case there 
        was a logger with the log name before.

        :copyright: (c) 2010 by Armin Ronacher.
        """
        Logger = getLoggerClass()

        class DebugLogger(Logger):
            def getEffectiveLevel(x):
                return DEBUG if self.sandbox else Logger.getEffectiveLevel(x)

        class DebugHandler(StreamHandler):
            def emit(x, record):
                StreamHandler.emit(x, record) if self.sandbox else None

        handler = DebugHandler()
        handler.setLevel(DEBUG)
        handler.setFormatter(Formatter(self.debug_log_format))
        logger = getLogger(self.logger_name)
        # just in case that was not a new logger, get rid of all the handlers
        # already attached to it.
        del logger.handlers[:]
        logger.__class__ = DebugLogger
        logger.addHandler(handler)
        return logger

    @property
    def logger(self):
        """A :class:`logging.Logger` object  

        This logger can be used to (surprise) log messages.

        Here some examples::

            self.logger.debug('Something to debug ')
            self.logger.warning('Final Warning : %s', 'I dont know')

        >>> import sys; sys.stderr = sys.stdout
        >>> c = BaseAPIClient('a', 'b', 'c', True)
        >>> c.logger
        <....DebugLogger instance at 0x...>
        >>> c.logger.debug('Test')
        -...
        DEBUG in ...:
        Test
        -...
        >>> c.sandbox = False
        >>> c._logger = None
        >>> c.logger.debug('Test')

        """
        if self._logger and self._logger.name == self.logger_name:
            return self._logger

        with _logger_lock:
            if self._logger and self._logger.name == self.logger_name:
                return self._logger
            self._logger = rv = self.create_logger()
            return rv

    def send_request(self, url, data):
        """Sends data to the server on a request
        """
        request = urllib2.Request(url=url, data=data.encode("utf-8"))
        return urllib2.urlopen(request).read()

    @classmethod
    def look_for_error(cls, response):
        """Looks for an element error and raises an exception out of it"""
        try:
            error = response.Response.Error
        except AttributeError:
            return None
        else:
            raise PyUPSException("%s-%s:%s" % (
                error.ErrorSeverity.pyval,
                error.ErrorCode.pyval,
                error.ErrorDescription.pyval,
                ))

    @property
    def access_request(self):
        """
        Returns the XML container for first part of any request

        >>> client = BaseAPIClient('license_no', 'user_id', 
        ...     'password', True
        ... )
        >>> client.access_request
        <Element AccessRequest at 0x...>
        >>> from lxml import etree
        >>> print etree.tostring(client.access_request, pretty_print=True)
        <AccessRequest>
          <Password>password</Password>
          <UserId>user_id</UserId>
          <AccessLicenseNumber>license_no</AccessLicenseNumber>
        </AccessRequest>
        <BLANKLINE>
        >>> 
        """
        return \
            E.AccessRequest( 
                E.Password(self.password),
                E.UserId(self.user_id),
                E.AccessLicenseNumber(self.license_no)
                )

    @classmethod
    def make_elements(cls, required_keys, args, kwargs):
        """Ensures that the given keys exist in either the elements list given
        by args or exist as keys in the kwargs (with their values). The kwargs
        are converted into elements with tags as their keys and the text as the
        value provided in the dict. Then the elements in args and kwargs are
        combined into a list and returned

        :param required_keys: An iterable of the required Keys
        :param kwargs: A dictionary of the key:value pairs to make elements
        :param args: A list of elements as positional args. Their tag attribute
            will be evaluated to check for existance 
        :return: a list of lxml Elements made out of key value pairs and args

        >>> BaseAPIClient.make_elements(['a', 'b'], [], {'a': '1', 'b': '2'})
        [<Element a at 0x...>, <Element b at 0x...>]
        >>> BaseAPIClient.make_elements(['a', 'b'], [E.b('2')], {'a': '1'})
        [<Element a at 0x...>, <Element b at 0x...>]
        >>> BaseAPIClient.make_elements(['a', 'b'], [], {'a': '1',})
        Traceback (most recent call last):
            ...
        ValueError: Attributes b is/are required.
        >>> BaseAPIClient.make_elements(['a', 'b', 'c'], [], {'a': '1',})
        Traceback (most recent call last):
            ...
        ValueError: Attributes c,b is/are required.

        """
        keys_set = frozenset(required_keys)
        args_keys = frozenset([e.tag for e in args])
        dict_keys_set = frozenset(kwargs.keys())

        # Diff = required_keys - elements in args - elements in the kwargs 
        difference = keys_set.difference(args_keys).difference(dict_keys_set)

        if difference:
            raise ValueError(
                'Attributes %s is/are required.' % ','.join(difference)
                )

        return [E(k, v) for k, v in kwargs.iteritems()] + list(args)


class ShipmentConfirm(BaseAPIClient):
    """Implements the ShipmentConfirmRequest"""

    # Indicates the action to be taken by the XML service.
    RequestAction = E.RequestAction('ShipConfirm')

    # Optional Processing 
    # nonvalidate = No address validation.
    # validate = Fail on failed address validation.
    #
    # Defaults to validate. Note: Full address validation is not performed. 
    # Therefore, it is the responsibility of the Shipping Tool User to ensure 
    # the address entered is correct to avoid an address correction fee.
    RequestOption = E.RequestOption('nonvalidate')

    # TransactionReference identifies transactions between client and server.
    TransactionReference = E.TransactionReference(
        E.CustomerContext('unspecified')
        )


    @classmethod
    def ship_phone_type(cls, *args, **kwargs):
        """Returns lXML Element for the phone_type

        :param Number: TODO
        :param Extension: TODO (Optional)

        >>> from lxml import etree
        >>> print etree.tostring(
        ...     ShipmentConfirm.ship_phone_type(
        ...         Number='number', Extension='extn'), 
        ...     pretty_print=True)
        <Phone>
          <Number>number</Number>
          <Extension>extn</Extension>
        </Phone>
        <BLANKLINE>
        """
        elements = cls.make_elements(['Number'], args, kwargs)
        return E.Phone(*elements)

    @classmethod
    def address_type(cls, *args, **kwargs):
        """Returns lXML Element for the address_type

        :param AddressLine1: Address Line 1 (Required)
        :param AddressLine2: Address Line 2 (Optional)
        :param AddressLine3: Address Line 3 (Optional)
        :param City: City (Required)
        :param StateProviceCode: Consignee's state or province code.(Optional)
            Required for US or Canada.
            If destination is US or CA, then the value
            must be a valid US State/Canadian
            Province code. If the country is Ireland, the
            StateProvinceCode will contain the county.
        :param CountryCode: Consignee's country code. (Required)

        Only for ShipTo Address (/ShipmentRequest/Shipment/ShipTo/Address)

        :param residential_address_indicator: This field is a flag to 
            indicate if the receiver is a residential location. True if
            ResidentialAddressIndicator tag exists; false otherwise


        >>> from lxml import etree
        >>> print etree.tostring(
        ...     ShipmentConfirm.address_type(
        ...         AddressLine1='Line1', City='City'), pretty_print=True)
        <Address>
          <City>City</City>
          <AddressLine1>Line1</AddressLine1>
        </Address>
        <BLANKLINE>
        >>> print etree.tostring(
        ...     ShipmentConfirm.address_type(
        ...         AddressLine1='Line1', AddressLine2='Line2', City='City'), 
        ...     pretty_print=True)
        <Address>
          <City>City</City>
          <AddressLine2>Line2</AddressLine2>
          <AddressLine1>Line1</AddressLine1>
        </Address>
        <BLANKLINE>
        """
        elements = cls.make_elements(('AddressLine1', 'City'), args, kwargs)

        # There seems to be no easy way to send the StateProvinceCode for the
        # states and provices outside CA and US. So generate a warning, if the
        # country is not US or CA and a StateProviceCode is given
        data = dict(((e.tag, e.text) for e in elements))
        if 'CountryCode' in data and 'StateProviceCode' in data \
            and data['CountryCode'] not in ('US', 'CA'):
            cls.logger.warn(
                "StateProvinceCode are required only for CA and US")

        return E.Address(*elements)

    @classmethod
    def shipper_type(cls, *args, **kwargs):
        """Returns the shipper data type.

        :param Name: (Required)
        :param ShipperNumber: (Required)
        :param AttentionName: (Required)
        :param TaxIdentificationNumber: (Required)
        :param PhoneNumber: (Required)
        :param FaxNumber: (Optional)
        :param EMailAddress: (Optional)
        :param Address: (Optional)
        :param LocationID: (Optional)
        """
        required_args = (
            'Name', 'AttentionName', 
            'TaxIdentificationNumber', 'PhoneNumber', 'ShipperNumber')
        elements = cls.make_elements(required_args, args, kwargs)
        return E.Shipper(*elements)

    @classmethod
    def ship_to_type(cls, *args, **kwargs):
        """Returns the ship to data type. (/ShipmentRequest/Shipment/ShipTo)
        :param CompanyName: (Required)
        :param AttentionName: (Required)
        :param TaxIdentificationNumber: (Required)
        :param PhoneNumber: (Required)
        :param FaxNumber: (Optional)
        :param EMailAddress: (Optional)
        :param Address: (Optional)
        :param LocationID: (Optional)
        """
        required_args = (
            'CompanyName', 'AttentionName', 
            'TaxIdentificationNumber', 'PhoneNumber',)
        elements = cls.make_elements(required_args, args, kwargs)
        return E.ShipTo(*elements)

    @classmethod
    def ship_from_type(cls, *args, **kwargs):
        """Returns the ship from data type (/ShipmentRequest/Shipment/ShipFrom)

        :param CompanyName: (Required)
        :param AttentionName: (Required)
        :param TaxIdentificationNumber: (Required)
        :param PhoneNumber: (Required)
        :param FaxNumber: (Optional)
        :param EMailAddress: (Optional)
        :param Address: (Optional)
        """
        required_args = (
            'CompanyName', 'AttentionName', 
            'TaxIdentificationNumber', 'PhoneNumber',)
        elements = cls.make_elements(required_args, args, kwargs)
        return E.ShipFrom(*elements)

    @classmethod
    @not_implemented_yet
    def sold_to_type(cls, *args, **kwargs):
        pass

    @classmethod
    @not_implemented_yet
    def credit_card_type(cls, *args, **kwargs):
        """
        Credit card information container
        Required if
        /ShipmentRequest/Shipment/PaymentInformation/ShipmentCharge/
        BillShipper/AccountNumber 
        is not present. Credit card payment is valid for shipments without
        return service only.
        """
        pass

    @classmethod
    def service_type(cls, *args, **kwargs):
        """
        UPS service type (This is as of the day of documenting, please
        check with the latest documentation of UPS for the same)

        :param Code : Values are: 
            01 = Next Day Air, 
            02 = 2nd Day Air, 
            03 = Ground, 
            07 = Express, 
            08 = Expedited, 
            11 = UPS Standard, 
            12 = 3 Day Select, 
            13 = Next Day Air Saver, 
            14 = Next Day Air Early AM, 
            54 = Express Plus, 
            59 = 2nd Day Air A.M., 
            65 = UPS Saver.
            82 = UPS Today Standard 
            83 = UPS Today Dedicated Courier 
            84 = UPS Today Intercity
            85 = UPS Today Express 
            86 = UPS Today Express Saver. 
            Note: Only service code 03 is used for 
                    Ground Freight Pricing shipments
        The following Services are not
        available to return shipment: 
            13 = Next Day Air Saver,
            14 = Next Day Air Early AM, 
            59 = 2nd Day Air A.M.
            82 = UPS Today Standard
            83 = UPS Today Dedicated Courier
            84 = UPS Today Intercity
            85 = UPS Today Express
            86 = UPS Today Express Saver.
        :param Description: Description of the service code. Examples
                            are Next Day Air, Worldwide Express, and
                            Ground.
        """
        elements = cls.make_elements(['Code'], args, kwargs)
        return E.Service(*elements)

    @classmethod
    def payment_information_prepaid_type(cls, *args, **kwargs):
        """
        A payment method must be specified for the Bill Shipper billing option.
        Therefore, either the AccountNumber child element or the CreditCard 
        child element must be provided, but not both.

        Container for the BillShipper billing option. The two payment methods 
        that are available for the Bill Shipper billing option are account 
        number or credit card.

        :param AccountNumber: Must be the same UPS account number as the one 
        provided in Shipper/ShipperNumber. Either this element or the sibling 
        element CreditCard must be provided, but both may not be provided.

        :param CreditCard: Not Implemented Yet.
        """
        # TODO: When credit card is implemented ensure that the Element tag is
        # CreditCard
        elements = cls.make_elements(['AccountNumber'], args, kwargs)
        return E.Prepaid(E.BillShipper(*elements))

    @classmethod
    def payment_information_type(cls, method):
        """
        This element or its sibling element, ItemizedPaymentInformation, must 
        be present but no more than one can be present. This API does not 
        implement ItemizedPaymentInformation yet.

        The method must be one of:

            Prepaid: Use :meth:`payment_information_prepaid_type`
            BillThirdParty: Use :meth:``
            FreightCollect: use :meth:``
        """
        return E.PaymentInformation(method)

    @classmethod
    def shipment_service_option_type(cls, *args, **kwargs):
        """Service Options:

        1. SaturdayDelivery: Available to all shipment types. 

        .. Warning::
            It may not be possible to book saturday deliveries more than two 
            days in advance. Or in other words, SatudayDelivery can usually be
            made only on bookings of Thrusday or Friday.
        """
        return E.ShipmentServiceOptions(*cls.make_elements([], args, kwargs))

    @classmethod
    def packaging_type(cls, *args, **kwargs):
        """
        Packaging Container
        Packaging type is required for Ground
        Freight Pricing Shipments only

        :param Code:01 = UPS Letter, 02 = Customer Supplied Package,
                    03 = Tube, 04 = PAK, 21 = UPS Express Box, 
                    24 = UPS 25KG Box, 25 = UPS 10KG Box
                    30 = Pallet
                    2a = Small Express Box
                    2b = Medium Express Box
                    2c = Large Express Box. 
            Note: Only packaging type code 02 is applicable to 
            Ground Freight Pricing
        :param Description: Anything sensible
        """
        elements = cls.make_elements(['Code'], args, kwargs)
        return E.PackagingType(*elements)

    @classmethod
    def package_weight_type(cls, Weight, *args, **kwargs):
        """
        :param Weight: Packages weight. (Required)
        :param Code: UnitOfMeasurement/Code (Required)
        :param Description: UnitOfMeasurement/Description (optional)
        """
        return E.PackageWeight(
            E.UnitOfMeasurement(*cls.make_elements([], args, kwargs)),
            E.Weight(Weight)
        )

    @classmethod
    def dimensions_type(cls, *args, **kwargs):
        """
        :param Code: UnitOfMeasurement/Code
        :param Description: UnitOfMeasurement/Description
        :param Length:
        :param Width:
        :param Height:
        """
        uom_dict = {
            'Code': kwargs['Code'],
            'Description': kwargs.get('Description', "")
            }
        return E.Dimensions(
            E.UnitOfMeasurement(*cls.make_elements(['Code'], [], uom_dict)),
            E.Length(kwargs['Length']),
            E.Width(kwargs['Width']),
            E.Height(kwargs['Height']),
            )


    @classmethod
    def package_type(cls, *args, **kwargs):
        """
        :param PackagingType: Generated from :meth:`packaging_type`
        :param Description: Merchandise Description of the Package (Optional)
        :param PackageWeight: Generated from :meth:`package_weight_type`
        :param Dimensions: Generated from :meth:`dimensions_type`
        """
        elements = cls.make_elements(
            ['PackagingType', 'PackageWeight', 'Dimensions'], args, kwargs)
        return E.Package(*elements)

    @classmethod
    def label_print_method_type(cls, *args, **kwargs):
        """The device used to print a label image.

        :param Code: Label print method code that the labels are  to be 
            generated for EPL2 formatted labels use EPL, for SPL formatted 
            labels use SPL, for ZPL formatted labels use ZPL, for STAR printer 
            formatted labels use STARPL and for image formats use GIF.

            For shipments without return service the valid value is GIF, EPL, 
            ZPL, STARPL and SPL. For shipments with PRL return service, the 
            valid values are EPL, ZPL, STARPL, SPL and GIF.

        :param Description: Label Specification Code description
        """
        values = {
            'Code': 'GIF'
            }
        values.update(kwargs)

        if args:
            len_args = len(args)
            expected_length = 2 - len(kwargs.keys())
            assert len_args == expected_length, \
                "Expected %d pos. args got %d" % (expected_length, len_args)

        return E.LabelPrintMethod(*cls.make_elements(['Code'], args, values))

    @classmethod
    def label_image_format_type(cls, *args, **kwargs):
        """Label image generation format

        :param Code: Required if 
            ShipmentConfirmRequest/LabelSpecification/LabelPrintMethod/Code is
            equal to GIF. 
            Valid values are GIF or PNG. Only GIF is supported on the remote 
            server.
        :param Description: (Optional)

        """
        values = {
            'Code': 'GIF'
            }
        values.update(kwargs)

        if args:
            len_args = len(args)
            expected_length = 2 - len(kwargs.keys())
            assert len_args == expected_length, \
                "Expected %d pos. args got %d" % (expected_length, len_args)

        return E.LabelImageFormat(*cls.make_elements(['Code'], args, values))

    @classmethod
    def label_specification_type(cls, *args, **kwargs):
        """

        :param LabelPrintMethod
        :param LabelImageFormat (optionally required if Print method is GIF)
        """
        return E.LabelSpecification(*cls.make_elements(
            ['LabelPrintMethod'], args, kwargs))


    @classmethod
    def shipment_confirm_request_type(cls, *args, **kwargs):
        """Builds a ShipmentConfirmRequest. All elements other than the 
        description are required.

        :param Shipper: Shipper Element generated by :meth:shipper_type
        :param ShipTo: ShipTo element generated by :meth:ship_to_type
        :param ShipFrom: ShipFrom element generated by :meth:ship_from_type
        :param Service: Service element generated by :meth:service_type
        :param PaymentInformation: PaymentInformation element generated by
            :meth: payment_information_type
        :param ShipmentServiceOptions: ShipmentServiceOptions element generated
            by :meth: shipment_service_options_type
        :param LabelSpecification: LabelSpecification option generated by the
            :meth: label_specification_type (Optional - defaults to GIF)
        :param Description: Description (optional)
        """

        # /ShipmentConfirmRequest/Request
        request = E.Request(
            cls.RequestAction,
            cls.RequestOption,
            cls.TransactionReference,
            )

        # Guess the LabelSpecification if nothing is provided
        # /ShipmentConfirmRequest/LabelSpecification
        if 'LabelSpecification' not in kwargs:
            label_specification = cls.label_specification_type(
                cls.label_print_method_type(),
                cls.label_image_format_type()
                )
        else:
            label_specification = kwargs.pop('LabelSpecification')

        # Construct the Shipment Element
        # /ShipmentConfirmRequest/Shipment/
        #
        # The first step is checking all arguments exists, which could be done 
        # for free by the :meth:`make_elements` but the result cannot be used
        # because the tags would be nested. Eg. Shipper would repeat in a level
        elements = cls.make_elements([
            'Shipper', 'ShipTo', 'ShipFrom',
            'Service', 'PaymentInformation', 
            ], args, kwargs)

        # The shipment element due to above reason is just generated from the 
        # values as the tag names already exist in the constructed element
        shipment_element = E.Shipment(*elements)

        # The full request consists of the Request, Shipment element and
        # the Label Specification
        # /ShipmentConfirmRequest/
        return E.ShipmentConfirmRequest(
            request, shipment_element, label_specification)

    @property
    def url(self):
        """Concatenates the URL with the Base URL"""
        return '/'.join([
            self.base_url[self.sandbox and 'sandbox' or 'production'],
            'ShipConfirm']
            )

    def request(self, shipment_confirm_request):
        """Calls up UPS and send the request. Get the returned response
        and return an element built out of it.

        :param shipment_confirm_request: lxml element with data for the
        shipment_confirm_request
        """
        full_request = '\n'.join([
            '<?xml version="1.0" encoding="UTF-8" ?>',
            etree.tostring(self.access_request, pretty_print=True),
            '<?xml version="1.0" encoding="UTF-8" ?>',
            etree.tostring(shipment_confirm_request, pretty_print=True),
            ])
        self.logger.debug("Request XML: %s", full_request)

        # Send the request
        result = self.send_request(self.url, full_request) 
        self.logger.debug("Response Received: %s", result)

        response = objectify.fromstring(result)
        self.look_for_error(response)
        return response

    @classmethod
    def extract_digest(cls, response):
        """Returns the Digest from the xml response

        :param response: lxml Element representing the response from UPS
        """
        return response.ShipmentDigest.pyval


class ShipmentAccept(BaseAPIClient):
    """Implements the ShipmentAcceptRequest"""

    # Indicates the action to be taken by the XML service.
    RequestAction = E.RequestAction('ShipAccept')

    # Optional Processing 
    # nonvalidate = No address validation.
    # validate = Fail on failed address validation.
    #
    # Defaults to validate. Note: Full address validation is not performed. 
    # Therefore, it is the responsibility of the Shipping Tool User to ensure 
    # the address entered is correct to avoid an address correction fee.
    RequestOption = E.RequestOption('nonvalidate')

    # TransactionReference identifies transactions between client and server.
    TransactionReference = E.TransactionReference(
        E.CustomerContext('unspecified')
        )

    @classmethod
    def shipment_accept_request_type(cls, digest):
        """
        """
        # /ShipmentAcceptRequest/Request
        request = E.Request(
            cls.RequestAction,
            cls.RequestOption,
            cls.TransactionReference,
            )

        # /ShipmentAcceptRequest/ShipmentDigest
        digest_element = E.ShipmentDigest(digest)

        return E.ShipmentAcceptRequest(request, digest_element)

    @property
    def url(self):
        """Concatenates the URL with the Base URL"""
        return '/'.join([
            self.base_url[self.sandbox and 'sandbox' or 'production'],
            'ShipAccept']
            )

    def request(self, shipment_accept_request):
        """Calls up UPS and send the request. Get the returned response
        and return an element built out of it.

        :param shipment_confirm_request: lxml element with data for the
        shipment_confirm_request
        """
        full_request = '\n'.join([
            '<?xml version="1.0" encoding="UTF-8" ?>',
            etree.tostring(self.access_request, pretty_print=True),
            '<?xml version="1.0" encoding="UTF-8" ?>',
            etree.tostring(shipment_accept_request, pretty_print=True),
            ])
        self.logger.debug("Request XML: %s", full_request)

        # Send the request
        result = self.send_request(self.url, full_request) 
        self.logger.debug("Response Received: %s", result)

        response =  objectify.fromstring(result)
        self.look_for_error(response)
        return response


if __name__ == '__main__':
    import doctest
    doctest.testmod(optionflags=doctest.ELLIPSIS)
