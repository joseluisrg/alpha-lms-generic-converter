FROM moodlehq/moodle-php-apache:8.4@sha256:093506f1d1dbdfaeaeb204793e17c5352329368914ab4ea7f7a9fc2a120e9269

USER root

COPY moodle-5.3.1.tgz /tmp/moodle.tgz
RUN tar -xzf /tmp/moodle.tgz --strip-components=1 -C /var/www/html \
    && rm -f /tmp/moodle.tgz \
    && mkdir -p /var/moodledata \
    && chown -R www-data:www-data /var/www/html /var/moodledata

EXPOSE 80
